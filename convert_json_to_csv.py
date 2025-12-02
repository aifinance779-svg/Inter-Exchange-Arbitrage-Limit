import json
import csv

input_file  = r"C:\Users\prath\.smartapi\OpenAPIScripMaster.json"
output_file = r"C:\Users\prath\.smartapi\OpenAPI_Instrument.csv"

with open(input_file, "r") as f:
    data = json.load(f)

with open(output_file, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["symbol", "token", "exchange", "tradingSymbol"])

    for item in data:
        writer.writerow([
            item.get("symbol", ""),
            item.get("token", ""),
            item.get("exch_seg", ""),
            item.get("tradingSymbol", "")
        ])

print("CSV saved successfully:", output_file)
