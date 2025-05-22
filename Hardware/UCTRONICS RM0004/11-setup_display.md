# Install DISPLAY Tool/Driver for UCTRONICS Rack Case

---

https://github.com/UCTRONICS/SKU_RM0004
https://github.com/UCTRONICS/UCTRONICS_RM0004_HA
https://github.com/UCTRONICS/HomeAssistant

---

If you use a UCTRONICS Rack Case with display, you will need to install the UCTRONICS display tool. First, copy the UCTRONICS display tool to the Raspberry Pi 4.

```bash
mv ./display /usr/local/bin
chmod 550 /usr/local/bin/display
chown root:root /usr/local/bin/display
```

After copying the display tool, create a service to start the display tool on boot.

```bash
vi /etc/systemd/system/uctronics-display.service
```

The file should look like this.

```service
[Unit]
Description=UCTRONICS Display

[Service]
ExecStart=/usr/local/bin/display
Restart=always
Type=simple

[Install]
WantedBy=multi-user.target
```

After creating the service, enable the service and reload the systemd daemon.

```bash
systemctl daemon-reload
systemctl enable uctronics-display.service
```

Edit your `/boot/firmware/config.txt` file...

```bash
vi /boot/firmware/config.txt
```

... and adde the following lines to the end of the file into the all section. Make sure that the lines are not duplicated.

```config
[all]
dtparam=i2c_arm=on,i2c_arm_baudrate=400000
dtoverlay=gpio-shutdown,gpio_pin=4,active_low=1,gpio_pull=up
```
