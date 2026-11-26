# Download dependencies only while building this trusted fixture image.
# Verification containers run offline with no network and no host credentials.
ARG JAVA_VERSION=17
FROM maven:3.9-eclipse-temurin-${JAVA_VERSION}
WORKDIR /opt/preload
COPY pom.xml ./pom.xml
COPY src ./src
RUN mvn -B -Dmaven.repo.local=/opt/maven-repository test && chmod -R a+rwX /opt/maven-repository
WORKDIR /workspace
