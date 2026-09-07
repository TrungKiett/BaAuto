"""Create the multi-size Windows icon for Web Automator Studio."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
ASSETS.mkdir(exist_ok=True)

SIZE = 1024


def rounded_mask(box, radius):
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle(box, radius=radius, fill=255)
    return mask


def vertical_gradient(top, bottom):
    image = Image.new("RGBA", (SIZE, SIZE))
    pixels = image.load()
    for y in range(SIZE):
        progress = y / (SIZE - 1)
        color = tuple(round(top[i] + (bottom[i] - top[i]) * progress) for i in range(4))
        for x in range(SIZE):
            pixels[x, y] = color
    return image


def add_glow(canvas, box, color, radius=36):
    glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(glow).rounded_rectangle(box, radius=radius, fill=color)
    canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(radius)))


def build_icon():
    icon = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))

    # Premium blue app tile with a subtle depth gradient.
    tile = vertical_gradient((11, 48, 121, 255), (4, 19, 62, 255))
    tile_mask = rounded_mask((26, 26, 998, 998), 230)
    icon.paste(tile, mask=tile_mask)

    overlay = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.ellipse((500, -150, 1200, 550), fill=(70, 188, 255, 55))
    overlay_draw.ellipse((-190, 580, 480, 1220), fill=(85, 96, 255, 55))
    overlay_draw.rounded_rectangle((46, 46, 978, 978), radius=210, outline=(132, 214, 255, 85), width=10)
    icon.alpha_composite(overlay)

    # A small circuit halo makes the automation purpose recognizable.
    circuit = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    circuit_draw = ImageDraw.Draw(circuit)
    circuit_color = (114, 223, 255, 175)
    circuit_draw.line((255, 346, 168, 346, 168, 254), fill=circuit_color, width=22, joint="curve")
    circuit_draw.line((769, 346, 856, 346, 856, 254), fill=circuit_color, width=22, joint="curve")
    circuit_draw.line((512, 208, 512, 156), fill=circuit_color, width=22)
    for cx, cy in ((168, 236), (856, 236), (512, 136)):
        circuit_draw.ellipse((cx - 34, cy - 34, cx + 34, cy + 34), fill=(198, 246, 255, 255))
        circuit_draw.ellipse((cx - 15, cy - 15, cx + 15, cy + 15), fill=(35, 157, 255, 255))
    icon.alpha_composite(circuit)

    # Bot shadow and ears.
    add_glow(icon, (244, 300, 780, 730), (12, 128, 255, 150), radius=54)
    bot = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    bot_draw = ImageDraw.Draw(bot)
    bot_draw.rounded_rectangle((218, 410, 288, 620), radius=34, fill=(77, 196, 255, 255))
    bot_draw.rounded_rectangle((736, 410, 806, 620), radius=34, fill=(77, 196, 255, 255))

    bot_mask = rounded_mask((254, 286, 770, 736), 126)
    bot_gradient = vertical_gradient((238, 250, 255, 255), (157, 222, 255, 255))
    bot.paste(bot_gradient, mask=bot_mask)
    bot_draw.rounded_rectangle((254, 286, 770, 736), radius=126, outline=(240, 253, 255, 255), width=14)
    bot_draw.rounded_rectangle((276, 308, 748, 714), radius=105, outline=(53, 151, 244, 190), width=12)

    # Eyes remain readable even in the smallest icon size.
    for left, right in ((340, 470), (554, 684)):
        bot_draw.rounded_rectangle((left, 426, right, 540), radius=54, fill=(8, 42, 100, 255))
        bot_draw.ellipse((left + 34, 454, left + 72, 492), fill=(91, 231, 255, 255))
        bot_draw.ellipse((left + 44, 464, left + 57, 477), fill=(244, 255, 255, 255))

    # A compact automation mark replaces a generic robot mouth.
    bot_draw.rounded_rectangle((405, 594, 619, 628), radius=17, fill=(15, 91, 187, 255))
    for x in (424, 494, 564):
        bot_draw.ellipse((x, 579, x + 64, 643), fill=(235, 252, 255, 255))
        bot_draw.ellipse((x + 16, 595, x + 48, 627), fill=(38, 164, 255, 255))

    # Antenna: the visual cue for an intelligent agent.
    bot_draw.line((512, 286, 512, 229), fill=(185, 241, 255, 255), width=22)
    bot_draw.ellipse((470, 176, 554, 260), fill=(208, 248, 255, 255), outline=(57, 173, 255, 255), width=12)
    bot_draw.ellipse((493, 199, 531, 237), fill=(42, 169, 255, 255))
    icon.alpha_composite(bot)

    # Diagonal sparkle gives the tile a polished, active feel.
    sparkle = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    sparkle_draw = ImageDraw.Draw(sparkle)
    sparkle_draw.polygon([(790, 714), (825, 801), (912, 836), (825, 871), (790, 958), (755, 871), (668, 836), (755, 801)], fill=(160, 239, 255, 235))
    sparkle_draw.polygon([(790, 763), (804, 822), (863, 836), (804, 850), (790, 909), (776, 850), (717, 836), (776, 822)], fill=(19, 114, 224, 255))
    icon.alpha_composite(sparkle)

    return icon


if __name__ == "__main__":
    final_icon = build_icon()
    final_icon.save(ASSETS / "web_automator_studio.png")
    final_icon.save(
        ASSETS / "web_automator_studio.ico",
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"Created {ASSETS / 'web_automator_studio.png'}")
    print(f"Created {ASSETS / 'web_automator_studio.ico'}")
