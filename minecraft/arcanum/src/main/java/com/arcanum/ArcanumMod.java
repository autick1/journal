package com.arcanum;

import com.arcanum.item.WandItem;
import com.arcanum.mana.Mana;
import com.arcanum.net.CastAnimPayload;
import com.arcanum.net.CycleSpellPayload;
import com.arcanum.net.ManaSyncPayload;
import com.arcanum.registry.ModBlocks;
import com.arcanum.registry.ModComponents;
import com.arcanum.registry.ModEntities;
import com.arcanum.registry.ModItems;
import com.arcanum.spell.Spells;
import com.arcanum.util.TaskScheduler;
import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.fabricmc.fabric.api.networking.v1.PayloadTypeRegistry;
import net.fabricmc.fabric.api.networking.v1.ServerPlayConnectionEvents;
import net.fabricmc.fabric.api.networking.v1.ServerPlayNetworking;
import net.minecraft.util.Identifier;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class ArcanumMod implements ModInitializer {
    public static final String MOD_ID = "arcanum";
    public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);

    public static Identifier id(String path) {
        return Identifier.of(MOD_ID, path);
    }

    @Override
    public void onInitialize() {
        ModComponents.init();
        ModBlocks.init();
        ModItems.init();
        ModEntities.init();
        Spells.init();
        Mana.init();

        PayloadTypeRegistry.playS2C().register(ManaSyncPayload.ID, ManaSyncPayload.CODEC);
        PayloadTypeRegistry.playS2C().register(CastAnimPayload.ID, CastAnimPayload.CODEC);
        PayloadTypeRegistry.playC2S().register(CycleSpellPayload.ID, CycleSpellPayload.CODEC);

        ServerPlayNetworking.registerGlobalReceiver(CycleSpellPayload.ID,
                (payload, ctx) -> WandItem.cycleSpell(ctx.player(), payload.direction()));

        ServerPlayConnectionEvents.JOIN.register((handler, sender, server) -> Mana.sync(handler.player));
        ServerTickEvents.END_SERVER_TICK.register(server -> {
            TaskScheduler.tick(server);
            Mana.tick(server);
        });

        LOGGER.info("Arcanum: {} spells loaded", Spells.all().size());
    }
}
