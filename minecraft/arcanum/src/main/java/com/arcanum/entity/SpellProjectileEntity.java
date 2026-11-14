package com.arcanum.entity;

import com.arcanum.registry.ModEntities;
import com.arcanum.spell.Spell;
import com.arcanum.spell.Spells;
import net.minecraft.entity.Entity;
import net.minecraft.entity.EntityType;
import net.minecraft.entity.LivingEntity;
import net.minecraft.entity.data.DataTracker;
import net.minecraft.entity.data.TrackedData;
import net.minecraft.entity.data.TrackedDataHandlerRegistry;
import net.minecraft.entity.projectile.thrown.ThrownEntity;
import net.minecraft.server.network.ServerPlayerEntity;
import net.minecraft.util.hit.HitResult;
import net.minecraft.util.math.Vec3d;
import net.minecraft.world.World;

/** Generic invisible magic projectile; visuals and effects come from its {@link Spell}. */
public class SpellProjectileEntity extends ThrownEntity {
    private static final TrackedData<String> SPELL = DataTracker.registerData(SpellProjectileEntity.class, TrackedDataHandlerRegistry.STRING);
    private static final TrackedData<Float> GRAVITY = DataTracker.registerData(SpellProjectileEntity.class, TrackedDataHandlerRegistry.FLOAT);

    /** Server-side state. */
    public float power = 1f;
    public int maxAge = 60;
    public int homingTarget = -1;
    public double speed = 1;
    public Vec3d target;

    public SpellProjectileEntity(EntityType<? extends SpellProjectileEntity> type, World world) {
        super(type, world);
    }

    public static SpellProjectileEntity create(World world, LivingEntity owner, Spell spell, Vec3d pos, Vec3d velocity, float gravity) {
        SpellProjectileEntity p = new SpellProjectileEntity(ModEntities.SPELL_PROJECTILE, world);
        p.setOwner(owner);
        p.setPosition(pos);
        p.setVelocity(velocity);
        p.speed = velocity.length();
        p.dataTracker.set(SPELL, spell.id);
        p.dataTracker.set(GRAVITY, gravity);
        return p;
    }

    @Override
    protected void initDataTracker(DataTracker.Builder builder) {
        builder.add(SPELL, "");
        builder.add(GRAVITY, 0f);
    }

    public Spell spell() {
        return Spells.get(dataTracker.get(SPELL));
    }

    public ServerPlayerEntity caster() {
        return getOwner() instanceof ServerPlayerEntity p ? p : null;
    }

    @Override
    protected double getGravity() {
        return dataTracker.get(GRAVITY);
    }

    @Override
    public void tick() {
        super.tick();
        if (isRemoved()) return;
        Spell spell = spell();
        if (spell == null) {
            if (!getWorld().isClient && age > 2) discard();
            return;
        }
        if (getWorld().isClient) {
            spell.projectileClientTick(this);
        } else {
            if (caster() == null) {
                discard();
                return;
            }
            spell.projectileTick(this);
            if (age >= maxAge && !isRemoved()) {
                spell.projectileExpire(this);
                discard();
            }
        }
    }

    /** Steers towards the homing target, keeping speed constant. */
    public void steer(double turnRate) {
        if (homingTarget < 0) return;
        Entity t = getWorld().getEntityById(homingTarget);
        if (t == null || !t.isAlive()) return;
        Vec3d want = t.getBoundingBox().getCenter().subtract(getPos()).normalize().multiply(speed);
        Vec3d v = getVelocity().multiply(1 - turnRate).add(want.multiply(turnRate));
        setVelocity(v.normalize().multiply(speed));
        velocityModified = true;
    }

    @Override
    protected boolean canHit(Entity entity) {
        return super.canHit(entity) && !(entity instanceof SpellProjectileEntity) && !(entity instanceof SpellZoneEntity);
    }

    @Override
    protected void onCollision(HitResult hit) {
        super.onCollision(hit);
        if (!getWorld().isClient && !isRemoved()) {
            Spell spell = spell();
            if (spell != null && caster() != null) spell.projectileHit(this, hit);
            discard();
        }
    }

    @Override
    public boolean shouldSave() {
        return false;
    }
}
