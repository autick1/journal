package com.arcanum.block;

import net.minecraft.block.Block;
import net.minecraft.block.BlockState;
import net.minecraft.particle.ParticleTypes;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.util.math.BlockPos;
import net.minecraft.util.math.Direction;
import net.minecraft.util.math.random.Random;
import net.minecraft.world.World;

/** A block created by a spell; it removes itself after {@code lifetime} ticks. */
public class ConjuredBlock extends Block {
    private final int lifetime;
    private final boolean glassy;

    public ConjuredBlock(Settings settings, int lifetime, boolean glassy) {
        super(settings);
        this.lifetime = lifetime;
        this.glassy = glassy;
    }

    @Override
    protected void onBlockAdded(BlockState state, World world, BlockPos pos, BlockState oldState, boolean notify) {
        super.onBlockAdded(state, world, pos, oldState, notify);
        if (!world.isClient && !oldState.isOf(this)) {
            world.scheduleBlockTick(pos, this, lifetime + world.random.nextInt(60));
        }
    }

    @Override
    protected void scheduledTick(BlockState state, ServerWorld world, BlockPos pos, Random random) {
        world.spawnParticles(glassy ? ParticleTypes.SNOWFLAKE : ParticleTypes.ENCHANT,
                pos.getX() + 0.5, pos.getY() + 0.5, pos.getZ() + 0.5, 8, 0.3, 0.3, 0.3, 0.02);
        world.breakBlock(pos, false);
    }

    @Override
    protected boolean isSideInvisible(BlockState state, BlockState stateFrom, Direction direction) {
        return (glassy && stateFrom.isOf(this)) || super.isSideInvisible(state, stateFrom, direction);
    }
}
