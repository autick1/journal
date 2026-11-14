package com.arcanum.spell;

import net.minecraft.entity.Entity;
import net.minecraft.entity.LivingEntity;
import net.minecraft.entity.decoration.ArmorStandEntity;
import net.minecraft.entity.player.PlayerEntity;
import net.minecraft.entity.projectile.ProjectileUtil;
import net.minecraft.particle.DustParticleEffect;
import net.minecraft.particle.ParticleEffect;
import net.minecraft.server.network.ServerPlayerEntity;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.sound.SoundCategory;
import net.minecraft.sound.SoundEvent;
import net.minecraft.util.hit.BlockHitResult;
import net.minecraft.util.hit.EntityHitResult;
import net.minecraft.util.hit.HitResult;
import net.minecraft.util.math.Box;
import net.minecraft.util.math.Vec3d;
import net.minecraft.world.RaycastContext;
import org.joml.Vector3f;

import java.util.List;

/** Targeting, damage and particle helpers shared by all spells. */
public final class SpellUtil {
    private SpellUtil() {}

    public static DustParticleEffect dust(int rgb, float scale) {
        return new DustParticleEffect(new Vector3f(((rgb >> 16) & 255) / 255f, ((rgb >> 8) & 255) / 255f, (rgb & 255) / 255f), scale);
    }

    public static boolean validTarget(Entity e, Entity caster) {
        return e instanceof LivingEntity l && l.isAlive() && e != caster && !(e instanceof ArmorStandEntity)
                && !(e instanceof PlayerEntity p && (p.isSpectator() || p.isCreative()));
    }

    /** Block raycast from the eyes. */
    public static BlockHitResult raycastBlocks(ServerPlayerEntity p, double dist) {
        Vec3d eye = p.getEyePos();
        Vec3d end = eye.add(p.getRotationVec(1f).multiply(dist));
        return p.getWorld().raycast(new RaycastContext(eye, end, RaycastContext.ShapeType.COLLIDER, RaycastContext.FluidHandling.NONE, p));
    }

    /** Combined block + entity raycast; returns null on a miss. */
    public static HitResult raycast(ServerPlayerEntity p, double dist) {
        Vec3d eye = p.getEyePos();
        Vec3d look = p.getRotationVec(1f);
        BlockHitResult block = raycastBlocks(p, dist);
        double max = block.getType() == HitResult.Type.MISS ? dist : block.getPos().distanceTo(eye);
        Vec3d end = eye.add(look.multiply(max));
        EntityHitResult ent = ProjectileUtil.getEntityCollision(p.getWorld(), p, eye, end,
                p.getBoundingBox().stretch(look.multiply(max)).expand(1), e -> validTarget(e, p));
        if (ent != null) return ent;
        return block.getType() == HitResult.Type.MISS ? null : block;
    }

    /** The point the caster is aiming at (hit point, or max distance along the look vector). */
    public static Vec3d aimPoint(ServerPlayerEntity p, double dist) {
        HitResult hit = raycast(p, dist);
        if (hit != null) return hit.getPos();
        return p.getEyePos().add(p.getRotationVec(1f).multiply(dist));
    }

    /** Ground position under the aim point (for area spells). */
    public static Vec3d aimGround(ServerPlayerEntity p, double dist) {
        BlockHitResult hit = raycastBlocks(p, dist);
        Vec3d pos = hit.getType() == HitResult.Type.MISS ? p.getEyePos().add(p.getRotationVec(1f).multiply(dist)) : hit.getPos();
        ServerWorld w = p.getServerWorld();
        net.minecraft.util.math.BlockPos bp = net.minecraft.util.math.BlockPos.ofFloored(pos.x, pos.y + 0.01, pos.z);
        for (int i = 0; i < 24 && !w.getBlockState(bp.down()).isSolidBlock(w, bp.down()) && bp.getY() > w.getBottomY(); i++) {
            bp = bp.down();
        }
        return new Vec3d(pos.x, bp.getY(), pos.z);
    }

    /** Best living target near the crosshair (within a cone defined by {@code minDot}) and in line of sight. */
    public static LivingEntity findTarget(ServerPlayerEntity p, double range, double minDot) {
        Vec3d eye = p.getEyePos();
        Vec3d look = p.getRotationVec(1f);
        Box box = p.getBoundingBox().stretch(look.multiply(range)).expand(range * 0.35);
        LivingEntity best = null;
        double bestScore = minDot;
        for (Entity e : p.getWorld().getOtherEntities(p, box, e -> validTarget(e, p))) {
            Vec3d to = e.getBoundingBox().getCenter().subtract(eye);
            double d = to.length();
            if (d > range || d < 0.01) continue;
            double dot = to.multiply(1 / d).dotProduct(look);
            if (dot > bestScore && p.canSee(e)) {
                bestScore = dot;
                best = (LivingEntity) e;
            }
        }
        return best;
    }

    public static List<LivingEntity> livingAround(ServerWorld w, Vec3d c, double r, Entity exclude) {
        return w.getEntitiesByClass(LivingEntity.class, new Box(c, c).expand(r),
                e -> validTarget(e, exclude) && e.getBoundingBox().getCenter().squaredDistanceTo(c) <= r * r);
    }

    public static void magicDamage(LivingEntity target, ServerPlayerEntity caster, Entity direct, float amount) {
        target.damage(caster.getDamageSources().indirectMagic(direct == null ? caster : direct, caster), amount);
    }

    public static void knock(Entity e, Vec3d dir, double strength, double up) {
        Vec3d d = dir.lengthSquared() < 1e-6 ? Vec3d.ZERO : dir.normalize();
        e.addVelocity(d.x * strength, up, d.z * strength);
        e.velocityModified = true;
    }

    public static void sound(ServerWorld w, Vec3d pos, SoundEvent s, float vol, float pitch) {
        w.playSound(null, pos.x, pos.y, pos.z, s, SoundCategory.PLAYERS, vol, pitch);
    }

    public static void burst(ServerWorld w, ParticleEffect e, Vec3d pos, int count, double spread, double speed) {
        w.spawnParticles(e, pos.x, pos.y, pos.z, count, spread, spread, spread, speed);
    }

    /** A particle line (optionally jagged, for lightning). */
    public static void line(ServerWorld w, ParticleEffect e, Vec3d a, Vec3d b, double step, double jitter) {
        Vec3d d = b.subtract(a);
        double len = d.length();
        int n = Math.max(1, (int) (len / step));
        for (int i = 0; i <= n; i++) {
            Vec3d p = a.add(d.multiply(i / (double) n));
            double j = (i == 0 || i == n) ? 0 : jitter;
            w.spawnParticles(e, p.x + (w.random.nextDouble() - 0.5) * j, p.y + (w.random.nextDouble() - 0.5) * j,
                    p.z + (w.random.nextDouble() - 0.5) * j, 1, 0, 0, 0, 0);
        }
    }

    /** Jagged lightning bolt made of connected particle segments. */
    public static void bolt(ServerWorld w, Vec3d a, Vec3d b, int color) {
        Vec3d d = b.subtract(a);
        int segs = Math.max(3, (int) (d.length() / 1.5));
        Vec3d prev = a;
        for (int i = 1; i <= segs; i++) {
            Vec3d next = a.add(d.multiply(i / (double) segs));
            if (i < segs) next = next.add((w.random.nextDouble() - 0.5) * 0.9, (w.random.nextDouble() - 0.5) * 0.9, (w.random.nextDouble() - 0.5) * 0.9);
            line(w, net.minecraft.particle.ParticleTypes.ELECTRIC_SPARK, prev, next, 0.25, 0.05);
            line(w, dust(color, 0.8f), prev, next, 0.35, 0.1);
            prev = next;
        }
    }

    /** Horizontal particle ring; with {@code outward > 0} the particles fly outward. */
    public static void ring(ServerWorld w, ParticleEffect e, Vec3d c, double radius, int count, double outward) {
        for (int i = 0; i < count; i++) {
            double a = Math.PI * 2 * i / count;
            double cx = Math.cos(a), cz = Math.sin(a);
            if (outward > 0) {
                w.spawnParticles(e, c.x + cx * radius, c.y, c.z + cz * radius, 0, cx, 0.05, cz, outward);
            } else {
                w.spawnParticles(e, c.x + cx * radius, c.y, c.z + cz * radius, 1, 0, 0, 0, 0);
            }
        }
    }
}
