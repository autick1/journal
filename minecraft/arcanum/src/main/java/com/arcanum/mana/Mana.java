package com.arcanum.mana;

import com.arcanum.ArcanumMod;
import com.arcanum.net.ManaSyncPayload;
import com.mojang.serialization.Codec;
import net.fabricmc.fabric.api.attachment.v1.AttachmentRegistry;
import net.fabricmc.fabric.api.attachment.v1.AttachmentType;
import net.fabricmc.fabric.api.networking.v1.ServerPlayNetworking;
import net.minecraft.entity.player.PlayerEntity;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.network.ServerPlayerEntity;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/** Player mana: stored as a persistent attachment on the server, mirrored to the owning client. */
public final class Mana {
    public static final float MAX = 100f;
    /** Mana regenerated per tick (5 per second). */
    public static final float REGEN_PER_TICK = 0.25f;

    @SuppressWarnings("UnstableApiUsage")
    public static final AttachmentType<Float> MANA = AttachmentRegistry.<Float>builder()
            .persistent(Codec.FLOAT)
            .copyOnDeath()
            .initializer(() -> MAX)
            .buildAndRegister(ArcanumMod.id("mana"));

    /** Client-side mirror, written by the client network handler. */
    public static float clientMana = MAX;
    public static float clientMax = MAX;

    private static final Map<UUID, Float> LAST_SYNCED = new ConcurrentHashMap<>();

    private Mana() {}

    public static void init() {}

    public static float get(PlayerEntity player) {
        if (player.getWorld().isClient) return clientMana;
        Float v = player.getAttached(MANA);
        return v == null ? MAX : v;
    }

    public static void set(ServerPlayerEntity player, float value) {
        player.setAttached(MANA, Math.max(0, Math.min(MAX, value)));
    }

    /** Spends mana if available. Creative players cast for free. */
    public static boolean consume(ServerPlayerEntity player, float amount) {
        if (player.isCreative()) return true;
        float cur = get(player);
        if (cur < amount) return false;
        set(player, cur - amount);
        return true;
    }

    public static void add(ServerPlayerEntity player, float amount) {
        set(player, get(player) + amount);
    }

    public static void tick(MinecraftServer server) {
        for (ServerPlayerEntity p : server.getPlayerManager().getPlayerList()) {
            float cur = get(p);
            if (cur < MAX && p.isAlive()) set(p, cur + REGEN_PER_TICK);
            Float last = LAST_SYNCED.get(p.getUuid());
            float now = get(p);
            if (last == null || Math.abs(last - now) >= 0.5f || (now >= MAX && last < MAX)) sync(p);
        }
    }

    public static void sync(ServerPlayerEntity player) {
        float v = get(player);
        LAST_SYNCED.put(player.getUuid(), v);
        ServerPlayNetworking.send(player, new ManaSyncPayload(v, MAX));
    }
}
