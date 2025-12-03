# Ubuntu Server 24.04 LTS Installation Steps

> [!IMPORTANT]
> THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## 1. SELECT LANGUAGE

- English

## 2. INSTALLER UPDATE AVAILABLE

- If prompted, update to the new installer

## 3. KEYBOARD CONFIGURATION

- Select the keyboard layout that matches your keyboard
- Layout: German
- Variant: German

## 4. CHOOSE TYPE OF INSTALL

- Ubuntu Server (minimized)

## 5. NETWORK CONNECTIONS

- Set manual IPv4 address
- Disable IPv6
- Create a network bond if you have multiple NICs and need redundancy or increased throughput

## 6. CONFIGURE PROXY

- Leave blank, or configure a proxy if needed

## 7. CONFIGURE UBUNTU ARCHIVE MIRROR

- Mirror address: <http://de.archive.ubuntu.com/ubuntu/> (for Germany - change to your local mirror if needed)

## 8. GUIDED STORAGE CONFIGURATION

- Custom storage layout.
  Recommended partitioning scheme for Ubuntu Server.
  Minimum 32GB disk space.

| MOUNTPOINT     | TYPE   | FS   | SIZE   | LABEL  | NAME          | VOLGROUP |
| -------------- | ------ | ---- | ------ | ------ | ------------- | -------- |
| /boot          | PART   | EXT4 | 1024MB | boot   |               |          |
| /boot/efi      | PART   | VFAT | 1024MB | efi    |               |          |
| vgSystem       | LVM-VG |      |        |        |               |          |
| /              | LVM-LV | EXT4 | 8192MB | root   | lvRoot        | vgSystem |
| /home          | LVM-LV | EXT4 | 2048MB | home   | lvHome        | vgSystem |
| /tmp           | LVM-LV | EXT4 | 1024MB | tmp    | lvTmp         | vgSystem |
| /var           | LVM-LV | EXT4 | 4096MB | var    | lvVar         | vgSystem |
| /var/crash     | LVM-LV | EXT4 | 1024MB | crash  | lvVarCrash    | vgSystem |
| /var/log       | LVM-LV | EXT4 | 4096MB | log    | lvVarLog      | vgSystem |
| /var/log/audit | LVM-LV | EXT4 | 4096MB | audit  | lvVarLogAudit | vgSystem |
| /var/tmp       | LVM-LV | EXT4 | 1024MB | vartmp | lvVarTmp      | vgSystem |
| swap           | LVM-LV | SWAP | 4096MB |        | lvSwap        | vgSystem |

- Additional storage for Rancher and Longhorn.
  It is recommended to use a separate disk for Rancher and Longhorn.
  Also, use separate physical disks for Rancher and Longhorn if available.

| MOUNTPOINT        | TYPE   | FS   | SIZE                     | LABEL    | NAME       | VOLGROUP                                                    |
| ----------------- | ------ | ---- | ------------------------ | -------- | ---------- | ----------------------------------------------------------- |
| /var/lib/rancher  | LVM-LV | EXT4 | Minimum 32GB recommended | rancher  | lvRancher  | vgSystem or other, if multiple physical disks are available |
| /var/lib/longhorn | LVM-LV | EXT4 | Minimum 32GB recommended | longhorn | lvLonghorn | vgSystem or other, if multiple physical disks are available |

- Please scale the partition sizes according to your needs.

## 9. PROFILE SETUP

- Your name: Enter the full name of the administrator account
- Your server's name: Enter the hostname of the server
- Pick a username: Enter the username of the administrator account
- Choose a password: Enter the password of the administrator account
- Confirm your password: Confirm the password of the administrator account

## 10. UPGRADE TO UBUNTU PRO

- Skip for now - You can enable Ubuntu Pro later.
- If you own a Ubuntu Pro license, feel free to activate it.

## 11. SSH SETUP

- Install OpenSSH server: Yes
- Import SSH identity: No – We will do this later via script
- Ensure password authentication is enabled; it will be disabled later via the hardening script
- ⚠️ Do not expose this server to the internet before hardening it ⚠️

## 12. FEATURED SERVER SNAPS

- Skip the installation of optional server snaps at this stage. You can install them later as needed.

## Wait until the installation and update process has finished

- Eject installation media (CD-ROM or USB stick)
- Press ENTER to reboot
