package com.arcanum.registry;

import com.arcanum.ArcanumMod;
import com.mojang.serialization.Codec;
import net.minecraft.component.ComponentType;
import net.minecraft.network.codec.PacketCodecs;
import net.minecraft.registry.Registries;
import net.minecraft.registry.Registry;

import java.util.List;
import java.util.function.UnaryOperator;

public final class ModComponents {
    /** Spell ids inscribed into a wand, in slot order. */
    public static final ComponentType<List<String>> WAND_SPELLS = register("wand_spells",
            b -> b.codec(Codec.STRING.listOf()).packetCodec(PacketCodecs.STRING.collect(PacketCodecs.toList())));
    /** Index of the currently selected slot of a wand. */
    public static final ComponentType<Integer> SELECTED_SPELL = register("selected_spell",
            b -> b.codec(Codec.INT).packetCodec(PacketCodecs.VAR_INT));
    /** Spell id stored on a spell scroll. */
    public static final ComponentType<String> SPELL = register("spell",
            b -> b.codec(Codec.STRING).packetCodec(PacketCodecs.STRING));

    private ModComponents() {}

    private static <T> ComponentType<T> register(String name, UnaryOperator<ComponentType.Builder<T>> op) {
        return Registry.register(Registries.DATA_COMPONENT_TYPE, ArcanumMod.id(name), op.apply(ComponentType.builder()).build());
    }

    public static void init() {}
}
