package com.arcanum.net;

import com.arcanum.ArcanumMod;
import net.minecraft.network.RegistryByteBuf;
import net.minecraft.network.codec.PacketCodec;
import net.minecraft.network.codec.PacketCodecs;
import net.minecraft.network.packet.CustomPayload;

/** Tells the caster's client to play a first-person wand animation. */
public record CastAnimPayload(int style, int color) implements CustomPayload {
    public static final Id<CastAnimPayload> ID = new Id<>(ArcanumMod.id("cast_anim"));
    public static final PacketCodec<RegistryByteBuf, CastAnimPayload> CODEC = PacketCodec.tuple(
            PacketCodecs.VAR_INT, CastAnimPayload::style, PacketCodecs.INTEGER, CastAnimPayload::color, CastAnimPayload::new);

    @Override
    public Id<? extends CustomPayload> getId() {
        return ID;
    }
}
