from src.core.tokens import TOKEN_MAP

for key in sorted(TOKEN_MAP):
    if key.startswith("SBIN") or key.startswith("TATASTEEL"):
        print(key, "->", TOKEN_MAP[key])