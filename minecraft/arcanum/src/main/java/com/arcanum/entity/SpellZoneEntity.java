package com.arcanum.entity;

import com.arcanum.registry.ModEntities;
import com.arcanum.spell.Spell;
import com.arcanum.spell.Spells;
import net.minecraft.entity.Entity;
import net.minecraft.entity.EntityType;
import net.minecraft.entity.data.DataTracker;
import net.minecraft.entity.data.TrackedData;
import net.minecraft.entity.data.TrackedDataHandlerRegistry;
import net.minecraft.nbt.NbtCompound;
import net.minecraft.server.network.ServerPlayerEntity;
import net.minecraft.util.math.Vec3d;
import net.minecraft.world.World;

import java.util.UUID;

/** A lingering spell area (blizzard, singularity...). Lives for a fixed time, then calls {@link Spell#zoneEnd}. */
public class SpellZoneEntity extends Entity {
    private static final TrackedData<String> SPELL = DataTracker.registerData(SpellZoneEntity.class, TrackedDataHandlerRegistry.STRING);
    private static final TrackedData<Float> RADIUS = DataTracker.registerData(SpellZoneEntity.class, TrackedDataHandlerRegistry.FLOAT);
    private static final TrackedData<Integer> DURATION = DataTracker.registerData(SpellZoneEntity.class, TrackedDataHandlerRegistry.INTEGER);

    public float power = 1f;
    private UUID ownerUuid;

    public SpellZoneEntity(EntityType<?> type, World world) {
        super(type, world);
        noClip = true;
    }

    public static SpellZoneEntity create(World world, ServerPlayerEntity owner, Spell spell, Vec3d pos, float radius, int duration, float power) {
        SpellZoneEntity z = new SpellZoneEntity(ModEntities.SPELL_ZONE, world);
        z.setPosition(pos);
        z.ownerUuid = owner.getUuid();
        z.power = power;
        z.dataTracker.set(SPELL, spell.id);
        z.dataTracker.set(RADIUS, radius);
        z.dataTracker.set(DURATION, duration);
        return z;
    }

    @Override
    protected void initDataTracker(DataTracker.Builder builder) {
        builder.add(SPELL, "");
        builder.add(RADIUS, 3f);
        builder.add(DURATION, 60);
    }

    public Spell spell() {
        return Spells.get(dataTracker.get(SPELL));
    }

    public float radius() {
        return dataTracker.get(RADIUS);
    }

    public int duration() {
        return dataTracker.get(DURATION);
    }

    public ServerPlayerEntity caster() {
        if (ownerUuid == null || getWorld().getServer() == null) return null;
        return getWorld().getServer().getPlayerManager().getPlayer(ownerUuid);
    }

    @Override
    public void tick() {
        super.tick();
        Spell spell = spell();
        if (spell == null) {
            if (!getWorld().isClient && age > 2) discard();
            return;
        }
        if (getWorld().isClient) {
            spell.zoneClientTick(this);
            return;
        }
        if (caster() == null) {
            discard();
            return;
        }
        spell.zoneTick(this);
        if (age >= duration()) {
            spell.zoneEnd(this);
            discard();
        }
    }

    @Override
    protected void readCustomDataFromNbt(NbtCompound nbt) {}

    @Override
    protected void writeCustomDataToNbt(NbtCompound nbt) {}

    @Override
    public boolean shouldSave() {
        return false;
    }
}
