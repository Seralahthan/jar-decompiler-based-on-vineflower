package com.test.java17;

public sealed class ShapeHierarchy permits ShapeHierarchy.Circle, ShapeHierarchy.Rect {
    public static final class Circle extends ShapeHierarchy {
        private final double radius;
        public Circle(double radius) { this.radius = radius; }
        public double area() { return Math.PI * radius * radius; }
    }

    public static final class Rect extends ShapeHierarchy {
        private final double w, h;
        public Rect(double w, double h) { this.w = w; this.h = h; }
        public double area() { return w * h; }
    }

    public static String describe(ShapeHierarchy s) {
        if (s instanceof Circle c) return "circle r=" + c.area();
        if (s instanceof Rect r) return "rect a=" + r.area();
        return "unknown";
    }
}
