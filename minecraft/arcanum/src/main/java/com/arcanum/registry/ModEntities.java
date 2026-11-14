package com.arcanum.registry;

import com.arcanum.ArcanumMod;
import com.arcanum.entity.SpellProjectileEntity;
import com.arcanum.entity.SpellZoneEntity;
import net.minecraft.entity.EntityType;
import net.minecraft.entity.SpawnGroup;
import net.minecraft.registry.Registries;
import net.minecraft.registry.Registry;

public final class ModEntities {
    public static final EntityType<SpellProjectileEntity> SPELL_PROJECTILE = Registry.register(Registries.ENTITY_TYPE,
            ArcanumMod.id("spell_projectile"),
            EntityType.Builder.<SpellProjectileEntity>create(SpellProjectileEntity::new, SpawnGroup.MISC)
                    .dimensions(0.3f, 0.3f).maxTrackingRange(8).trackingTickInterval(1).build("spell_projectile"));

    public static final EntityType<SpellZoneEntity> SPELL_ZONE = Registry.register(Registries.ENTITY_TYPE,
            ArcanumMod.id("spell_zone"),
            EntityType.Builder.<SpellZoneEntity>create(SpellZoneEntity::new, SpawnGroup.MISC)
                    .dimensions(0.5f, 0.5f).makeFireImmune().maxTrackingRange(10).trackingTickInterval(5).build("spell_zone"));

    private ModEntities() {}

    public static void init() {}
}
