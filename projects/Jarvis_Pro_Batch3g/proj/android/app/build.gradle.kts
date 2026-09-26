plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.jarvis.companion"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.jarvis.companion"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"
        // No server address or token is baked into the build (BUG 2).
    }

    buildTypes {
        debug {
            isMinifyEnabled = false
            // Debug allows cleartext to private LAN addresses only.
            manifestPlaceholders["networkSecurityConfig"] =
                "@xml/network_security_config"
        }
        release {
            isMinifyEnabled = false
            // Release forbids cleartext entirely: wss:// required (BUG 3).
            manifestPlaceholders["networkSecurityConfig"] =
                "@xml/network_security_config_release"
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    testOptions {
        unitTests.isReturnDefaultValues = true
    }
}

dependencies {
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("androidx.security:security-crypto:1.1.0-alpha06")
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
}
