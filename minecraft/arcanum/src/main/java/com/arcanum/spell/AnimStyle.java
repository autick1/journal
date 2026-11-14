package com.arcanum.spell;

/** First-person wand gesture played when a spell is cast. Durations are in ticks. */
public enum AnimStyle {
    FLICK(8), THRUST(8), SWIRL(12), SLAM(12), SWEEP(10), RAISE(14), STAB(7), CHANNEL(6);

    public final int duration;

    AnimStyle(int duration) {
        this.duration = duration;
    }
}
