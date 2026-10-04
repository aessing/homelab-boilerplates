import types
import stat
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / '43-configure-host-maintenance.sh'
SOURCE = SCRIPT.read_text().split("<<'PYTHON'\n", 1)[1].rsplit('\nPYTHON', 1)[0]
HELPER = types.ModuleType('host_maintenance')
exec(compile(SOURCE, str(SCRIPT), 'exec'), HELPER.__dict__)


class HostMaintenanceTests(unittest.TestCase):
    def test_ssh_preserves_includes_and_match_blocks(self):
        original = 'Include /etc/ssh/sshd_config.d/*.conf\nMatch User service\n    AllowTcpForwarding no\n'
        candidate = HELPER.ssh_candidate(original)
        self.assertTrue(candidate.endswith(original))
        self.assertLess(candidate.index('PermitRootLogin no'), candidate.index('\nInclude '))
        self.assertEqual(HELPER.ssh_candidate(candidate), candidate)

    def test_existing_safe_ssh_directive_is_unchanged(self):
        original = '# policy\nPermitRootLogin no\nInclude /etc/ssh/sshd_config.d/*.conf\n'
        self.assertEqual(HELPER.ssh_candidate(original), original)

    def test_different_explicit_ssh_policy_requires_review(self):
        for value in ('yes', 'prohibit-password', 'forced-commands-only'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                HELPER.ssh_candidate('PermitRootLogin ' + value + '\n')

    def test_match_policy_is_not_silently_overwritten(self):
        with self.assertRaises(ValueError):
            HELPER.ssh_candidate('Include /etc/ssh/sshd_config.d/*.conf\nMatch User backup\nPermitRootLogin yes\n')

    def test_rkhunter_disables_hook_without_changing_cron(self):
        original = '# policy\nCRON_DAILY_RUN="yes"\nAPT_AUTOGEN="yes" # apt hook\n'
        candidate = HELPER.rkhunter_candidate(original)
        self.assertIn('CRON_DAILY_RUN="yes"\n', candidate)
        self.assertIn('APT_AUTOGEN="no" # apt hook\n', candidate)
        self.assertEqual(HELPER.rkhunter_candidate(candidate), candidate)

    def test_rkhunter_existing_no_is_unchanged(self):
        original = "APT_AUTOGEN='no'\nCRON_DAILY_RUN='yes'\n"
        self.assertEqual(HELPER.rkhunter_candidate(original), original)

    def test_rkhunter_missing_key_gets_explicit_safe_value(self):
        original = 'CRON_DAILY_RUN="yes"'
        candidate = HELPER.rkhunter_candidate(original)
        self.assertIn('CRON_DAILY_RUN="yes"\n', candidate)
        self.assertIn('APT_AUTOGEN="no"\n', candidate)

    def test_rkhunter_refuses_ambiguous_or_executable_values(self):
        for original in ('APT_AUTOGEN=yes\nAPT_AUTOGEN=no\n',
                         'APT_AUTOGEN=$(something)\n',
                         'export APT_AUTOGEN=yes\n'):
            with self.subTest(original=original), self.assertRaises(ValueError):
                HELPER.rkhunter_candidate(original)

    def test_rkhunter_web_quotes_removed_without_enabling_network(self):
        for value in ('"/bin/false"', "'/bin/false'"):
            original = '# policy\nWEB_CMD=' + value + '\nUPDATE_MIRRORS=0\n'
            candidate = HELPER.rkhunter_web_candidate(original)
            self.assertEqual(candidate, '# policy\nWEB_CMD=/bin/false\nUPDATE_MIRRORS=0\n')
            self.assertEqual(HELPER.rkhunter_web_candidate(candidate), candidate)

    def test_rkhunter_web_comment_and_spacing_preserved(self):
        candidate = HELPER.rkhunter_web_candidate('  WEB_CMD = "/bin/false" # block downloads\n')
        self.assertEqual(candidate, '  WEB_CMD = /bin/false # block downloads\n')

    def test_rkhunter_web_other_commands_are_not_replaced(self):
        for original in ('WEB_CMD=wget\n', 'WEB_CMD="/some/other command"\n', '#WEB_CMD="/bin/false"\n'):
            self.assertEqual(HELPER.rkhunter_web_candidate(original), original)

    def test_rkhunter_web_duplicate_key_is_rejected(self):
        with self.assertRaises(ValueError):
            HELPER.rkhunter_web_candidate('WEB_CMD="/bin/false"\nWEB_CMD=wget\n')

    def marker(self, uid=0, mode=stat.S_IFREG | 0o644):
        data = (b'# This file was created by systemd-update-done. Its only \n'
                b'# purpose is to hold a timestamp of the time this directory\n'
                b'# was updated. See man:systemd-update-done.service(8).\n'
                b'TIMESTAMP_NSEC=1739607186000000000\n')
        return data, types.SimpleNamespace(st_uid=uid, st_mode=mode)

    def test_verified_systemd_marker_gets_only_exact_exception(self):
        data, info = self.marker()
        original = 'ALLOWHIDDENFILE=/etc/.pwd.lock\nWEB_CMD=/bin/false\n'
        candidate = HELPER.rkhunter_hidden_candidate(original, data, info)
        self.assertTrue(candidate.startswith(original))
        self.assertEqual(candidate.count('ALLOWHIDDENFILE=/etc/.updated\n'), 1)
        self.assertNotIn('ALLOWHIDDENFILE=/etc/.*', candidate)
        self.assertEqual(HELPER.rkhunter_hidden_candidate(candidate, data, info), candidate)

    def test_missing_marker_does_not_add_exception(self):
        original = 'WEB_CMD=/bin/false\n'
        self.assertEqual(HELPER.rkhunter_hidden_candidate(original, None, None), original)

    def test_marker_wrong_owner_mode_or_symlink_are_rejected(self):
        for uid, mode in ((1000, stat.S_IFREG | 0o644), (0, stat.S_IFREG | 0o666),
                          (0, stat.S_IFREG | 0o600), (0, stat.S_IFLNK | 0o644)):
            data, info = self.marker(uid, mode)
            with self.subTest(uid=uid, mode=mode), self.assertRaises(ValueError):
                HELPER.rkhunter_hidden_candidate('', data, info)

    def test_marker_full_content_must_match_even_with_existing_exception(self):
        data, info = self.marker()
        for changed in (data + b'extra\n', data.replace(b'TIMESTAMP_NSEC=', b'OTHER='), b'TIMESTAMP_NSEC=1\n'):
            with self.subTest(data=changed), self.assertRaises(ValueError):
                HELPER.rkhunter_hidden_candidate('ALLOWHIDDENFILE=/etc/.updated\n', changed, info)

    def test_marker_existing_quoted_or_glob_exception_requires_review(self):
        data, info = self.marker()
        for text in ('ALLOWHIDDENFILE="/etc/.updated"\n', 'ALLOWHIDDENFILE=/etc/.updated*\n'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                HELPER.rkhunter_hidden_candidate(text, data, info)

    def test_fwupd_adds_only_supported_plugin_key(self):
        original = '[fwupd]\n# comment\nOnlyTrusted=true\n[redfish]\nUri=https://example.invalid\n'
        candidate = HELPER.fwupd_candidate(original)
        self.assertEqual(HELPER.disabled_plugins(candidate), ['flashrom'])
        self.assertIn('# comment\nOnlyTrusted=true\n[redfish]\nUri=https://example.invalid\n', candidate)
        self.assertEqual(HELPER.fwupd_candidate(candidate), candidate)

    def test_fwupd_preserves_existing_disabled_plugins(self):
        original = '[fwupd]\nDisabledPlugins = test;uefi_capsule\nOnlyTrusted=true\n'
        candidate = HELPER.fwupd_candidate(original)
        self.assertEqual(HELPER.disabled_plugins(candidate), ['test', 'uefi_capsule', 'flashrom'])
        self.assertIn('OnlyTrusted=true', candidate)
        self.assertEqual(HELPER.fwupd_candidate(candidate), candidate)

    def test_fwupd_handles_missing_section_and_final_newline(self):
        for original in ('', '[redfish]\nUri=https://example.invalid', '[fwupd]'):
            with self.subTest(original=original):
                candidate = HELPER.fwupd_candidate(original)
                self.assertEqual(HELPER.disabled_plugins(candidate), ['flashrom'])

    def test_fwupd_preserves_existing_wildcard_exclusions(self):
        original = '[fwupd]\nDisabledPlugins=test*;invalid;flashrom\n'
        self.assertEqual(HELPER.fwupd_candidate(original), original)

    def test_fwupd_rejects_ambiguous_duplicate_settings(self):
        for original in ('[fwupd]\nDisabledPlugins=test\nDisabledPlugins=invalid\n',
                         '[fwupd]\nDisabledPlugins=test\n[fwupd]\nOnlyTrusted=true\n'):
            with self.subTest(original=original), self.assertRaises(Exception):
                HELPER.fwupd_candidate(original)

    def test_fwupd_rejects_unreviewed_plugin_list_syntax(self):
        with self.assertRaises(ValueError):
            HELPER.fwupd_candidate('[fwupd]\nDisabledPlugins=test,invalid\n')


if __name__ == '__main__':
    unittest.main()
