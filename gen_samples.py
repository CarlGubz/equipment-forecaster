import csv, random
from datetime import date, timedelta

random.seed(42)
TODAY = date(2026, 8, 31)
START = TODAY - timedelta(days=730)  # 2 years of history

# (part_number, part_name, machine/category, cadence_days, cadence_noise, qty_range)
CLIENTS = {
    "Acme Manufacturing": {
        "columns": ["Client", "Order Date", "SKU", "Part Description", "Qty", "Machine"],
        "date_fmt": "%m/%d/%Y",
        "parts": [
            ("SPN-2201", "Spindle Bearing",  "CNC Mill A3",   90, 7,  (1, 2)),
            ("CLF-118",  "Coolant Filter",   "CNC Mill A3",   30, 4,  (2, 6)),
            ("DRB-540",  "Drive Belt",       "Lathe L2",     120, 10, (1, 2)),
            ("THLD-330", "Tool Holder",      "CNC Mill A3",  180, 14, (1, 1)),
            ("WAYO-005", "Way Oil (20L)",    "Lathe L2",      45, 5,  (1, 3)),
        ],
    },
    "BluePeak Logistics": {
        "columns": ["account", "date_ordered", "item_code", "item_name", "units", "equipment_type"],
        "date_fmt": "%Y-%m-%d",
        "parts": [
            ("CR-8801",  "Conveyor Roller",  "Belt Conveyor 4",  75,  6,  (2, 5)),
            ("HYD-220",  "Hydraulic Hose",   "Forklift FL-7",    60,  6,  (1, 3)),
            ("FT-455",   "Forklift Tire",    "Forklift FL-7",   150, 12,  (2, 4)),
            ("CHN-090",  "Chain Link Kit",   "Belt Conveyor 4",  40,  4,  (1, 2)),
            ("BAT-1200", "Battery Cell",     "Forklift FL-7",   200, 15,  (1, 1)),
        ],
    },
    "Nordic Steel Works": {
        # European date format + different header language/style
        "columns": ["Kunde", "Purchase_Dt", "MaterialNo", "Component", "Amount", "AssetClass"],
        "date_fmt": "%d.%m.%Y",
        "parts": [
            ("ELC-770",  "Furnace Electrode",  "Arc Furnace 1",  50,  5,  (2, 4)),
            ("RLB-390",  "Roller Bearing",     "Rolling Mill 2", 110, 9,  (1, 2)),
            ("RFB-260",  "Refractory Brick",   "Arc Furnace 1",  35,  4,  (10, 24)),
            ("CLN-140",  "Cooling Nozzle",     "Rolling Mill 2", 90,  8,  (2, 5)),
            ("HSL-610",  "Hydraulic Seal",     "Rolling Mill 2", 70,  6,  (1, 3)),
        ],
    },
}

def gen_orders(parts):
    rows = []
    for pn, name, machine, cadence, noise, qtyr in parts:
        # start each part at a random offset so last-order dates vary
        d = START + timedelta(days=random.randint(0, cadence))
        while d <= TODAY:
            rows.append((d, pn, name, machine, random.randint(*qtyr)))
            step = max(7, int(random.gauss(cadence, noise)))
            d = d + timedelta(days=step)
    rows.sort(key=lambda r: r[0])
    return rows

for client, cfg in CLIENTS.items():
    rows = gen_orders(cfg["parts"])
    fmt = cfg["date_fmt"]
    cols = cfg["columns"]
    fname = client.lower().replace(" ", "_") + ".csv"
    with open(f"sample_data/{fname}", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for d, pn, name, machine, qty in rows:
            w.writerow([client, d.strftime(fmt), pn, name, qty, machine])
    print(f"{fname}: {len(rows)} rows, last date {max(r[0] for r in rows)}")
