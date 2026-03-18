package com.test.java17;

public record PointRecord(int x, int y) {
    public double distance() {
        return Math.sqrt(x * x + y * y);
    }
}
