package com.test.java21;

import java.util.LinkedHashMap;
import java.util.SequencedMap;

public class ModernPatterns {
    public String categorize(Object obj) {
        return switch (obj) {
            case Integer i when i > 0 -> "positive int: " + i;
            case String s -> "string: " + s;
            case null -> "null";
            default -> "other";
        };
    }

    public String firstKey(LinkedHashMap<String, Integer> map) {
        SequencedMap<String, Integer> seq = map;
        return seq.firstEntry().getKey();
    }
}
