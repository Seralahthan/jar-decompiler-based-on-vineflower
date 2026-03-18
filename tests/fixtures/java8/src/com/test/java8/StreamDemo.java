package com.test.java8;

import java.util.Arrays;
import java.util.List;
import java.util.function.Function;
import java.util.stream.Collectors;

public class StreamDemo {
    private List<String> names = Arrays.asList("Alice", "Bob", "Charlie");

    public List<String> getUpperNames() {
        return names.stream()
            .filter(n -> n.length() > 3)
            .map(String::toUpperCase)
            .collect(Collectors.toList());
    }

    public int sumLengths(Function<String, Integer> mapper) {
        return names.stream().map(mapper).reduce(0, Integer::sum);
    }
}
