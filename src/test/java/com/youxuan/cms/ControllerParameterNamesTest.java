package com.youxuan.cms;

import org.junit.jupiter.api.Test;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import static org.assertj.core.api.Assertions.assertThat;

class ControllerParameterNamesTest {
    @Test void routeBindingsDoNotDependOnCompilerParameterMetadata() {
        for (Class<?> controller : new Class<?>[]{PublicController.class, AdminApiController.class,
                MediaController.class, ImportController.class}) {
            for (var method : controller.getDeclaredMethods()) {
                for (var parameter : method.getParameters()) {
                    var query = parameter.getAnnotation(RequestParam.class);
                    if (query != null) assertThat(query.name().isBlank() && query.value().isBlank())
                        .as("Explicit request parameter name in %s", method).isFalse();
                    var path = parameter.getAnnotation(PathVariable.class);
                    if (path != null) assertThat(path.name().isBlank() && path.value().isBlank())
                        .as("Explicit path parameter name in %s", method).isFalse();
                }
            }
        }
    }
}
