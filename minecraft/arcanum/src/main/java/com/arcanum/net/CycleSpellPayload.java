package com.arcanum.net;

import com.arcanum.ArcanumMod;
import net.minecraft.network.RegistryByteBuf;
import net.minecraft.network.codec.PacketCodec;
import net.minecraft.network.codec.PacketCodecs;
import net.minecraft.network.packet.CustomPayload;

/** Client asks to switch the selected spell of the held wand (+1 / -1). */
public record CycleSpellPayload(int direction) implements CustomPayload {
    public static final Id<CycleSpellPayload> ID = new Id<>(ArcanumMod.id("cycle_spell"));
    public static final PacketCodec<RegistryByteBuf, CycleSpellPayload> CODEC = PacketCodec.tuple(
            PacketCodecs.VAR_INT, CycleSpellPayload::direction, CycleSpellPayload::new);

    @Override
    public Id<? extends CustomPayload> getId() {
        return ID;
    }
}
