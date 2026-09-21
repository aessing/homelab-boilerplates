# Install Display Tool/Driver for UCTRONICS RM0004 Rack Case

> [!IMPORTANT]
> THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

If you’re using a UCTRONICS RM0004 Rack Case with a built-in display, you need to install and configure the UCTRONICS display tool on your Raspberry Pi 4.

## Install the Display Tool

First, copy the UCTRONICS display tool to the target location.

```bash
sudo install -m 550 -o root -g root ./display /usr/local/bin/display
```

## Create a Systemd Service

To ensure the display tool starts automatically at boot, create a systemd service.

```bash
sudo tee /etc/systemd/system/uctronics-display.service > /dev/null << 'EOF'
[Unit]
Description=UCTRONICS Display

[Service]
ExecStart=/usr/local/bin/display
Restart=always
Type=simple

[Install]
WantedBy=multi-user.target
EOF
```

Then reload systemd and enable the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable uctronics-display.service
```

You can start it immediately with:

```bash
sudo systemctl start uctronics-display.service
```

## Configure Firmware

To enable I²C and GPIO shutdown for the display, you need to modify the firmware configuration:

1. Open the configuration file

```bash
vi /boot/firmware/config.txt
```

1. Add the following lines at the end of the file (make sure they are not already present)

```ini
[all]
dtparam=i2c_arm=on,i2c_arm_baudrate=400000
dtoverlay=gpio-shutdown,gpio_pin=4,active_low=1,gpio_pull=up
```

1. Save the file and reboot:

```bash
sudo reboot
```

## Links to the UCTRONICS RM0004 Repositries

- <https://github.com/UCTRONICS/SKU_RM0004>
- <https://github.com/UCTRONICS/UCTRONICS_RM0004_HA>
- <https://github.com/UCTRONICS/HomeAssistant>
