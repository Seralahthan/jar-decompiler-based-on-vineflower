package com.test.java8;

import java.util.Comparator;

public class LambdaHolder {
    public static final Comparator<String> BY_LENGTH = Comparator.comparingInt(String::length);

    @FunctionalInterface
    public interface Transformer<T> {
        T transform(T input);
    }

    public String apply(String input, Transformer<String> t) {
        return t.transform(input);
    }
}
