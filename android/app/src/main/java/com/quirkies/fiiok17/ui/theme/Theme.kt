package com.quirkies.fiiok17.ui.theme

import android.app.Activity
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat

val Charcoal900 = Color(0xFF0F1117)
val Charcoal800 = Color(0xFF181C26)
val Charcoal700 = Color(0xFF222836)
val Charcoal600 = Color(0xFF2E3648)
val AmberAccent = Color(0xFFFF9F1C)
val AmberGlow = Color(0xFFFFBF69)
val CyanAccent = Color(0xFF2EC4B6)
val TextPrimary = Color(0xFFF4F4F9)
val TextSecondary = Color(0xFF9E9EAF)
val DangerRed = Color(0xFFE63946)

private val DarkColorScheme = darkColorScheme(
    primary = AmberAccent,
    onPrimary = Color.Black,
    primaryContainer = Charcoal700,
    onPrimaryContainer = AmberGlow,
    secondary = CyanAccent,
    onSecondary = Color.Black,
    secondaryContainer = Charcoal600,
    onSecondaryContainer = Color.White,
    background = Charcoal900,
    onBackground = TextPrimary,
    surface = Charcoal800,
    onSurface = TextPrimary,
    surfaceVariant = Charcoal700,
    onSurfaceVariant = TextSecondary,
    error = DangerRed,
    onError = Color.White
)

@Composable
fun FiiOK17Theme(
    content: @Composable () -> Unit
) {
    val colorScheme = DarkColorScheme
    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as Activity).window
            window.statusBarColor = colorScheme.background.toArgb()
            window.navigationBarColor = colorScheme.background.toArgb()
            WindowCompat.getInsetsController(window, view).isAppearanceLightStatusBars = false
            WindowCompat.getInsetsController(window, view).isAppearanceLightNavigationBars = false
        }
    }

    MaterialTheme(
        colorScheme = colorScheme,
        content = content
    )
}
