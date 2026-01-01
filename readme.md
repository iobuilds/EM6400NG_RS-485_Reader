# EM6400NG RS-485 Reader (Modbus RTU) — Python GUI

A simple cross-platform Python GUI to read **Conzerv EM6400NG** energy meter data over **RS-485 (Modbus RTU)** using a **USB–RS485 converter**.

## Features
- Select available serial ports
- Configure baud rate, parity, slave ID, polling interval
- Connect / Disconnect
- Live table view of key registers (energy, voltage, current, power)

---

## Requirements
- macOS / Windows / Linux
- Python 3.10+ (your setup works with Python 3.13 + Tkinter)
- USB–RS485 converter (CH340 / FTDI / CP210x etc.)
- EM6400NG meter configured for Modbus RTU

---

## Project Structure

softwares/
├── em6400ng_gui.py
├── images/
│   └── logo.png
└── venv/                # created during setup

---

## Wiring (RS-485)
Connect the USB–RS485 converter to the meter:

- **A(+) → A(+)**
- **B(-) → B(-)**
- (Optional) Connect **GND → GND** if your converter provides it

> Tip: If you get no response, try swapping A/B lines.

---

## Meter Communication Settings (Recommended)
Set these in the meter:
- **Protocol:** Modbus RTU
- **Address (Slave ID):** 1 (or your configured ID)
- **Baud rate:** 19200
- **Parity:** Even (E)
- **Stop bits:** 1
- **Format:** 8E1

(Your GUI default values match: **19200, Even, 8E1, Slave=1**)

---

## Setup (macOS / Linux)

### 1) Go to project folder
```bash
cd /Volumes/512SSD/Projects/BBJSENSE/softwares

2) Create a virtual environment (venv)

Use a Python that supports Tkinter.

Example (macOS framework Python):

/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m venv venv

3) Activate venv

source venv/bin/activate

4) Install dependencies

pip install --upgrade pip
pip install pyserial pymodbus pillow

5) Run the GUI

python em6400ng_gui.py


⸻

Setup (Windows)

1) Open PowerShell in project folder

cd C:\path\to\softwares

2) Create venv

python -m venv venv

3) Activate venv

venv\Scripts\activate

4) Install dependencies

pip install --upgrade pip
pip install pyserial pymodbus pillow

5) Run

python em6400ng_gui.py


⸻

How to Use
	1.	Plug the USB–RS485 adapter into the PC
	2.	Open the app
	3.	Select the correct Port
	•	macOS typically shows /dev/cu.usbserial-* or /dev/cu.usbmodem-*
	4.	Set:
	•	Baud: 19200
	•	Parity: E
	•	Slave ID: 1
	•	Poll: 1000 ms (or adjust)
	5.	Click Connect
	6.	Values will update automatically

⸻

Troubleshooting

No ports or wrong port
	•	Click Refresh
	•	macOS: check available ports:

ls /dev/cu.*


	•	Windows: check COM ports in Device Manager

“ERR” or no values
	•	Confirm meter settings: Modbus RTU / Slave ID / Baud / Parity
	•	Check RS-485 wiring (swap A/B if needed)
	•	Ensure only one master is on the RS485 bus

Values are nonsense (very large / negative)

Try enabling:
	•	✅ Swap 16-bit words (if values wrong)

Some meters store float words in different order.

Permission error (Linux)

Add your user to dialout group:

sudo usermod -a -G dialout $USER

Then log out and log in again.

⸻

Register list

Edit the DEFAULT_REGS list inside em6400ng_gui.py to add/remove Modbus offsets.

⸻

Notes
	•	The app reads 32-bit float values (2 Modbus registers per item).
	•	Energies are currently read using Function Code 3 (Holding Registers) and measurements using Function Code 4 (Input Registers).
	•	If your meter uses FC=4 for energy too, change those items’ fc=4.

⸻

License

Internal / private use.

