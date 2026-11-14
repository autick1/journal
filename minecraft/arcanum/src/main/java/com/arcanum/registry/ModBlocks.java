package com.arcanum.registry;

import com.arcanum.ArcanumMod;
import com.arcanum.block.ConjuredBlock;
import net.minecraft.block.AbstractBlock;
import net.minecraft.block.Block;
import net.minecraft.block.MapColor;
import net.minecraft.block.piston.PistonBehavior;
import net.minecraft.registry.Registries;
import net.minecraft.registry.Registry;
import net.minecraft.sound.BlockSoundGroup;

public final class ModBlocks {
    /** Temporary magical ice (ice bridge). Melts away after ~25 s. */
    public static final Block CONJURED_ICE = register("conjured_ice", new ConjuredBlock(AbstractBlock.Settings.create()
            .mapColor(MapColor.PALE_PURPLE).strength(0.4f).slipperiness(0.98f).sounds(BlockSoundGroup.GLASS)
            .nonOpaque().luminance(s -> 7).dropsNothing().pistonBehavior(PistonBehavior.DESTROY)
            .allowsSpawning((s, w, p, t) -> false).solidBlock((s, w, p) -> false)
            .suffocates((s, w, p) -> false).blockVision((s, w, p) -> false), 500, true));
    /** Temporary rune stone (stone wall). Crumbles after ~15 s. */
    public static final Block CONJURED_STONE = register("conjured_stone", new ConjuredBlock(AbstractBlock.Settings.create()
            .mapColor(MapColor.STONE_GRAY).strength(1.5f, 6f).sounds(BlockSoundGroup.DEEPSLATE_BRICKS)
            .luminance(s -> 4).dropsNothing().pistonBehavior(PistonBehavior.BLOCK)
            .allowsSpawning((s, w, p, t) -> false), 300, false));

    private ModBlocks() {}

    private static Block register(String name, Block block) {
        return Registry.register(Registries.BLOCK, ArcanumMod.id(name), block);
    }

    public static void init() {}
}
