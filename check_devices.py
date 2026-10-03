import sounddevice as sd

print("default device:", sd.default.device)
print()
for i, d in enumerate(sd.query_devices()):
    marker = " <- default input" if i == sd.default.device[0] else ""
    print(f"{i}: {d['name']}  in={d['max_input_channels']}  out={d['max_output_channels']}{marker}")