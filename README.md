# AS511 PLC Tool

A Step 5 (S5) PLC tool that replaces the DOS STEP 5 interface.

It lets you:

* Talk to Siemens S5 PLCs over AS511 (serial or Profibus adapters)
* Download and upload data blocks, function blocks, OBs—you name it
* Compare PLC blocks against a local baseline with regex filtering (perfect for nightly diffs)
* Simple dark‑mode GUI built with CustomTkinter

Replaces the DOS STEP 5 interface with a straightforward Python tool.

---

## What’s inside?

* **`as511_core.py`**
  Core client code that speaks AS511, handles framing/LRC, and implements read/write/info.

* **`as511_gui_modern.py`**
  A clean, dark‑mode GUI (CustomTkinter) with three tabs:

  * **Download** – grab all blocks of a given type and save them locally
  * **Upload** – push a folder of `.bin` block files back into the PLC
  * **Compare** – regex‑filter by block type (e.g. `FB`) and diff against your baseline

---

## Getting started

1. **Install Python 3.8+**
2. Clone or drop these files into a folder
3. Install dependencies:

   ```bash
   pip install pyserial customtkinter
   ```
4. Launch the GUI:

   ```bash
   python as511_gui_modern.py
   ```
5. Point it at your serial adapter (e.g. `/dev/ttyUSB0` or `COM1`), set baud/addr, and you’re good to go!

---

## Tips & Tricks

* You can use **hex** or **decimal** for the Type ID (e.g. `0x08` or `8`).
* Baseline compare uses a simple naming scheme: `block_<TYPEHEX>_<NUM>.bin`. Keep your backups named like that.
* If you want to script everything, just import `as511_core.ExtendedAS511Client` in your own Python code.

---

## License

I dont know yet :)

## References
https://www.runmode.com/as511protocol_description.pdf
https://as511.sourceforge.net/protokolle/protokoll.html
