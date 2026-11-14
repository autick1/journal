package com.arcanum.spell;

import net.minecraft.text.Text;
import net.minecraft.util.Formatting;

public enum Element {
    ARCANE(0x7FB8FF, Formatting.AQUA),
    FIRE(0xFF6A2A, Formatting.GOLD),
    FROST(0x8FE6FF, Formatting.AQUA),
    STORM(0xFFD84A, Formatting.YELLOW),
    NATURE(0x5FD35F, Formatting.GREEN),
    VOID(0xA259FF, Formatting.LIGHT_PURPLE);

    public final int color;
    public final Formatting formatting;

    Element(int color, Formatting formatting) {
        this.color = color;
        this.formatting = formatting;
    }

    public String key() {
        return name().toLowerCase();
    }

    public Text displayName() {
        return Text.translatable("element.arcanum." + key()).formatted(formatting);
    }
}
