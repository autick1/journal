package com.arcanum.spell;

public enum CastType {
    /** Fires on right click. */
    INSTANT,
    /** Hold right click to charge, release to cast. */
    CHARGED,
    /** Hold right click; the effect runs every tick and drains mana. */
    CHANNEL
}
