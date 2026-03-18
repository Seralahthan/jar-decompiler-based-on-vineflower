package com.test.java21;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class VirtualThreadDemo {
    public void runTasks(int count) throws Exception {
        try (ExecutorService exec = Executors.newVirtualThreadPerTaskExecutor()) {
            for (int i = 0; i < count; i++) {
                final int id = i;
                exec.submit(() -> {
                    System.out.println("Task " + id);
                });
            }
        }
    }
}
