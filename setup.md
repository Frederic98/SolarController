# Setup OS
```shell
sudo apt update
sudo apt upgrade
sudo reboot
sudo apt install python3-pip git pigpio python3-pigpio
```
## Enable hardware interfaces
Using `sudo raspi-config`:  
Enable SPI: `Interface Options` > `SPI` > `Enable? [YES]`  
Enable UART: `Interface Options` > `Serial Port` > `Shell? [NO]` > `Enable? [YES]`

## Enable services
```shell
sudo cp systemd/* /etc/systemd/system/
sudo systemctl enable pigpiod solar-api solar-ui solar-ssh
sudo systemctl start pigpiod solar-api solar-ui solar-ssh
```

## [Install Node-Red](https://nodered.org/docs/getting-started/raspberrypi)
```shell
bash <(curl -sL https://raw.githubusercontent.com/node-red/linux-installers/master/deb/update-nodejs-and-nodered)
sudo systemctl enable nodered
sudo systemctl start nodered
```
### Enable user authentication
https://nodered.org/docs/user-guide/runtime/securing-node-red#editor--admin-api-security
```shell
nano ~/.node-red/settings.js
```
Uncomment the adminAuth block, and fill in the username and hashed password from `node-red admin hash-pw`
### Move Solar Controller nodes to the top of the palette
In `settings.js` under `editorTheme` > `palette` > `categories`, add `'Solar Controller'` to the start of the list

# ToDo:
- Enable overlayfs with seperate writeable /home partition
- Install node-red modules