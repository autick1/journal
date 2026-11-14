package com.arcanum.spell;

import com.arcanum.entity.SpellProjectileEntity;
import com.arcanum.entity.SpellZoneEntity;
import net.minecraft.text.Text;
import net.minecraft.util.hit.HitResult;

/**
 * Base class of every spell. A spell is data (cost, cooldown, element, gesture) plus behaviour hooks.
 * Projectile and zone spells also receive callbacks from their entities.
 */
public abstract class Spell {
    public final String id;
    public final Element element;
    public final CastType type;
    /** Mana per cast (for CHANNEL spells: mana per second). */
    public final int mana;
    public final int cooldown;
    public final int chargeTicks;
    public final AnimStyle anim;

    protected Spell(String id, Element element, CastType type, int mana, int cooldown, int chargeTicks, AnimStyle anim) {
        this.id = id;
        this.element = element;
        this.type = type;
        this.mana = mana;
        this.cooldown = cooldown;
        this.chargeTicks = chargeTicks;
        this.anim = anim;
    }

    public Text name() {
        return Text.translatable("spell.arcanum." + id);
    }

    public Text description() {
        return Text.translatable("spell.arcanum." + id + ".desc");
    }

    /** INSTANT / CHARGED: perform the spell. Return false to refund mana (e.g. no valid target). */
    public boolean cast(SpellContext ctx) {
        return false;
    }

    /** CHANNEL: called every tick while the use key is held. Return false to stop channelling. */
    public boolean channel(SpellContext ctx, int ticksUsed) {
        return false;
    }

    // ---- projectile hooks ----
    public void projectileTick(SpellProjectileEntity p) {}

    public void projectileClientTick(SpellProjectileEntity p) {}

    public void projectileHit(SpellProjectileEntity p, HitResult hit) {}

    public void projectileExpire(SpellProjectileEntity p) {}

    // ---- zone hooks ----
    public void zoneTick(SpellZoneEntity zone) {}

    public void zoneClientTick(SpellZoneEntity zone) {}

    public void zoneEnd(SpellZoneEntity zone) {}
}
