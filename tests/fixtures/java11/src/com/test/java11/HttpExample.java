package com.test.java11;

import java.util.Optional;

public class HttpExample {
    public Optional<String> findValue(String key) {
        return Optional.ofNullable(key).filter(k -> !k.isEmpty());
    }

    public String orDefault(Optional<String> opt) {
        return opt.orElse("default");
    }
}
