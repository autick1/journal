package com.arcanum.util;

import net.minecraft.server.MinecraftServer;

import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

/** Runs delayed actions on the server thread (used for staggered missiles, rising walls, ice bridges...). */
public final class TaskScheduler {
    private record Task(long dueTick, Runnable action) {}

    private static final List<Task> TASKS = new ArrayList<>();
    private static final List<Task> PENDING = new ArrayList<>();
    private static long tick;

    private TaskScheduler() {}

    public static void later(int delayTicks, Runnable action) {
        PENDING.add(new Task(tick + Math.max(1, delayTicks), action));
    }

    public static void tick(MinecraftServer server) {
        tick++;
        TASKS.addAll(PENDING);
        PENDING.clear();
        Iterator<Task> it = TASKS.iterator();
        List<Task> due = new ArrayList<>();
        while (it.hasNext()) {
            Task t = it.next();
            if (t.dueTick <= tick) {
                due.add(t);
                it.remove();
            }
        }
        for (Task t : due) {
            try {
                t.action.run();
            } catch (Exception e) {
                com.arcanum.ArcanumMod.LOGGER.error("Arcanum scheduled task failed", e);
            }
        }
    }
}
