package com.arcanum.spell;

import com.arcanum.item.WandStats;
import net.minecraft.item.ItemStack;
import net.minecraft.server.network.ServerPlayerEntity;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.util.math.Vec3d;

/** Everything a spell needs to know while it is being cast. */
public record SpellContext(ServerWorld world, ServerPlayerEntity caster, ItemStack wand, WandStats stats, Spell spell, float charge) {

    /** Damage/strength multiplier: wand power, element affinity and charge bonus. */
    public float power() {
        float p = stats.power() * charge;
        if (stats.affinity() == spell.element) p *= 1.4f;
        return p;
    }

    public Vec3d eye() {
        return caster.getEyePos();
    }

    public Vec3d look() {
        return caster.getRotationVec(1f);
    }

    /** Approximate world position of the wand tip (right hand, slightly forward). */
    public Vec3d handPos() {
        Vec3d look = look();
        Vec3d right = look.crossProduct(new Vec3d(0, 1, 0)).normalize();
        if (right.lengthSquared() < 1e-4) right = new Vec3d(1, 0, 0);
        boolean leftHanded = caster.getMainArm() == net.minecraft.util.Arm.LEFT;
        return eye().add(look.multiply(0.6)).add(right.multiply(leftHanded ? -0.3 : 0.3)).add(0, -0.25, 0);
    }

    public Vec3d horizontalLook() {
        Vec3d l = look();
        Vec3d h = new Vec3d(l.x, 0, l.z);
        return h.lengthSquared() < 1e-4 ? new Vec3d(0, 0, 1) : h.normalize();
    }
}
