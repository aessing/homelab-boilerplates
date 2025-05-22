# Configure a Raspberry Pi 4

### Set parameters for Raspberry Pi 4

Set the boot parameters for the Raspberry Pi 4.

```bash
vi /boot/firmware/config.txt
```

If you use a normal Raspberry Pi 4 case without display and need for GPIO, your config.txt should look like this.

```config
[all]
arm_64bit=1
kernel=vmlinuz
cmdline=cmdline.txt
initramfs initrd.img followkernel

# Enable the audio output, I2C and SPI interfaces on the GPIO header. As these
# parameters related to the base device-tree they must appear *before* any
# other dtoverlay= specification
#dtparam=audio=on
#dtparam=i2c_arm=on
#dtparam=spi=on

# Comment out the following line if the edges of the desktop appear outside
# the edges of your display
disable_overscan=1

# If you have issues with audio, you may try uncommenting the following line
# which forces the HDMI output into HDMI mode instead of DVI (which doesn't
# support audio output)
#hdmi_drive=2

# Enable the KMS ("full" KMS) graphics overlay, leaving GPU memory as the
# default (the kernel is in control of graphics memory with full KMS)
dtoverlay=vc4-kms-v3d
disable_fw_kms_setup=1

# Enable the serial pins
#enable_uart=1

# Autoload overlays for any recognized cameras or displays that are attached
# to the CSI/DSI ports. Please note this is for libcamera support, *not* for
# the legacy camera stack
camera_auto_detect=0
display_auto_detect=1

# Config settings specific to arm64
dtoverlay=dwc2

[pi4]
max_framebuffers=2
arm_boost=1

[pi3+]
# Use a smaller contiguous memory area, specifically on the 3A+ to avoid an
# OOM oops on boot. The 3B+ is also affected by this section, but it shouldn't
# cause any issues on that board
dtoverlay=vc4-kms-v3d,cma-128

[pi02]
# The Zero 2W is another 512MB board which is occasionally affected by the same
# OOM oops on boot.
dtoverlay=vc4-kms-v3d,cma-128

[cm4]
# Enable the USB2 outputs on the IO board (assuming your CM4 is plugged into
# such a board)
dtoverlay=dwc2,dr_mode=host

[all]
disable_splash=1
dtoverlay=disable-wifi
dtoverlay=disable-bt
gpu_mem=16
```

### Configure Networking

For servers, the networking should be configured with a fixed IP address.

To accomplish that, we need to configure the netplan configuration.

```bash
vi /etc/netplan/99_config.yaml
```

This is how an example configuration looks like. Please adjust the IP address, nameserver, search domain, and route to your needs.

```yaml
network:
  version: 2
  renderer: networkd
  ethernets:
    eth0:
      addresses:
        - '192.168.1.101/24'
      nameservers:
        addresses:
          - 192.168.1.1
        search:
          - fqdn.example.com
      routes:
        - to: 'default'
          via: '192.168.1.1'
```

At least, we need to apply the configuration and remove the cloud-init configuration.

```bash
chmod 400 /etc/netplan/99_config.yaml
rm /etc/netplan/50-cloud-init.yaml
netplan try
```

### Reboot

After setting up everything, please reboot the Raspberry Pi 4.

```bash
reboot
```
