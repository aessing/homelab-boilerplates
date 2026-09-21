# UCTRONICS RM0004 Rack Case

> [!IMPORTANT]
> THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

This folder contains configuration and setup files for the [UCTRONICS RM0004](https://www.uctronics.com/cluster-and-rack-mount/for-raspberry-pi/1u-rack-mount/uctronics-pi-rack-pro-for-raspberry-pi-4b-19-1u-rack-mount-support-for-4-2-5-ssds.html) 1U Raspberry Pi rack mount case. The RM0004 features a built-in OLED display that shows system information for each mounted Raspberry Pi.

## Prerequisites

- Raspberry Pi 4 Model B
- UCTRONICS RM0004 rack case with OLED display
- Ubuntu or Raspberry Pi OS

## Structure

```text
UCTRONICS RM0004/
├── 11-setup_display.md           # Display setup instructions
├── display                       # Display binary (placeholder)
├── HomeAssistant-master.zip      # Home Assistant integration
├── SKU_RM0004-main.zip           # Official UCTRONICS driver
└── UCTRONICS_RM0004_HA-main.zip  # Home Assistant add-on
```

## Configuration

### Display Driver

The OLED display requires a driver binary to show system information. The driver communicates via I²C and displays:

- IP address
- CPU usage
- Memory usage
- Storage usage
- CPU temperature

### Firmware Settings

The following settings must be added to `/boot/firmware/config.txt`:

| Setting | Description |
|---------|-------------|
| `dtparam=i2c_arm=on` | Enable I²C interface |
| `i2c_arm_baudrate=400000` | Set I²C speed to 400kHz |
| `dtoverlay=gpio-shutdown` | Enable GPIO shutdown button |
| `gpio_pin=4` | Use GPIO 4 for shutdown |

## Usage

1. Download the display binary from the official UCTRONICS repository:

   ```bash
   wget https://github.com/UCTRONICS/SKU_RM0004/raw/main/display
   ```

2. Follow the setup instructions in `11-setup_display.md` to:
   - Install the display binary
   - Create a systemd service
   - Configure firmware settings

3. Reboot to apply changes:

   ```bash
   sudo reboot
   ```

## Useful Commands

### Check Display Service Status

```bash
sudo systemctl status uctronics-display.service
```

### View Display Logs

```bash
journalctl -u uctronics-display.service -f
```

### Verify I²C Configuration

```bash
sudo i2cdetect -y 1
```

## Troubleshooting

### Display Not Working

1. Verify I²C is enabled:

   ```bash
   ls /dev/i2c*
   ```

2. Check if the service is running:

   ```bash
   sudo systemctl status uctronics-display.service
   ```

3. Verify firmware configuration:

   ```bash
   grep -E "i2c|gpio" /boot/firmware/config.txt
   ```

### Service Fails to Start

1. Check service logs:

   ```bash
   journalctl -u uctronics-display.service --no-pager
   ```

2. Verify binary permissions:

   ```bash
   ls -la /usr/local/bin/display
   ```

3. Ensure the binary is executable:

   ```bash
   sudo chmod +x /usr/local/bin/display
   ```

## References

- [UCTRONICS SKU_RM0004 GitHub](https://github.com/UCTRONICS/SKU_RM0004)
- [UCTRONICS Home Assistant Integration](https://github.com/UCTRONICS/UCTRONICS_RM0004_HA)
- [UCTRONICS HomeAssistant Add-on](https://github.com/UCTRONICS/HomeAssistant)
- [UCTRONICS Product Page](https://www.uctronics.com/cluster-and-rack-mount/for-raspberry-pi/1u-rack-mount/uctronics-pi-rack-pro-for-raspberry-pi-4b-19-1u-rack-mount-support-for-4-2-5-ssds.html)
