package com.arcanum.net;

import com.arcanum.ArcanumMod;
import net.minecraft.network.RegistryByteBuf;
import net.minecraft.network.codec.PacketCodec;
import net.minecraft.network.codec.PacketCodecs;
import net.minecraft.network.packet.CustomPayload;

public record ManaSyncPayload(float mana, float max) implements CustomPayload {
    public static final Id<ManaSyncPayload> ID = new Id<>(ArcanumMod.id("mana"));
    public static final PacketCodec<RegistryByteBuf, ManaSyncPayload> CODEC = PacketCodec.tuple(
            PacketCodecs.FLOAT, ManaSyncPayload::mana, PacketCodecs.FLOAT, ManaSyncPayload::max, ManaSyncPayload::new);

    @Override
    public Id<? extends CustomPayload> getId() {
        return ID;
    }
}
