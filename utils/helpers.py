import random


def randomize_case(value: str) -> str:
    """Рандомно меняет регистр букв, гарантируя минимум 1 изменение."""
    chars = list(value)
    alpha_indices = [i for i, c in enumerate(chars) if c.isalpha()]

    if not alpha_indices:
        return value

    forced = random.choice(alpha_indices)
    for i, char in enumerate(chars):
        if char.isalpha():
            if i == forced:
                chars[i] = char.upper() if char.islower() else char.lower()
            else:
                chars[i] = char.upper() if random.choice([True, False]) else char.lower()

    return "".join(chars)
