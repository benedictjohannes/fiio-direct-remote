package com.quirkies.fiiok17.widget

import android.content.Context
import android.content.Intent
import androidx.compose.runtime.Composable
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.glance.*
import androidx.glance.action.ActionParameters
import androidx.glance.action.actionParametersOf
import androidx.glance.action.actionStartActivity
import androidx.glance.action.clickable
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.GlanceAppWidgetManager
import androidx.glance.appwidget.action.ActionCallback
import androidx.glance.appwidget.action.actionRunCallback
import androidx.glance.appwidget.cornerRadius
import androidx.glance.appwidget.provideContent
import androidx.glance.layout.*
import androidx.glance.text.FontWeight
import androidx.glance.text.Text
import androidx.glance.text.TextStyle
import androidx.glance.unit.ColorProvider
import com.quirkies.fiiok17.R
import com.quirkies.fiiok17.data.K17Backend
import com.quirkies.fiiok17.data.K17Protocol
import com.quirkies.fiiok17.ui.MainActivity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class K17Widget : GlanceAppWidget() {

    override suspend fun provideGlance(context: Context, id: GlanceId) {
        val backend = K17Backend.getInstance(context)
        val status = backend.statusFlow.value

        provideContent {
            GlanceTheme {
                WidgetContent(status = status, context = context)
            }
        }
    }

    @Composable
    private fun WidgetContent(status: com.quirkies.fiiok17.data.K17Status, context: Context) {
        val backgroundColor = androidx.compose.ui.graphics.Color(0xFF161922)
        val cardBg = androidx.compose.ui.graphics.Color(0xFF212635)
        val accentColor = androidx.compose.ui.graphics.Color(0xFFFF9500)
        val textColor = androidx.compose.ui.graphics.Color(0xFFEDEDED)
        val dimText = androidx.compose.ui.graphics.Color(0xFF9E9E9E)

        Box(
            modifier = GlanceModifier
                .fillMaxSize()
                .background(backgroundColor)
                .cornerRadius(16.dp)
                .padding(12.dp)
        ) {
            if (status.isOnline) {
                // Active State
                Column(
                    modifier = GlanceModifier.fillMaxSize(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    // Header Row: Input Badge, Volume, Open App
                    Row(
                        modifier = GlanceModifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        // Input Badge button (tap to cycle)
                        Box(
                            modifier = GlanceModifier
                                .background(cardBg)
                                .cornerRadius(8.dp)
                                .padding(horizontal = 8.dp, vertical = 4.dp)
                                .clickable(actionRunCallback<CycleModeActionCallback>())
                        ) {
                            Text(
                                text = "🔀 ${status.inputMode?.shortName ?: "INPUT"}",
                                style = TextStyle(
                                    color = ColorProvider(accentColor),
                                    fontSize = 12.sp,
                                    fontWeight = FontWeight.Bold
                                )
                            )
                        }

                        Spacer(modifier = GlanceModifier.defaultWeight())

                        // Volume readout (Tap to open app)
                        Text(
                            text = "${status.volume ?: "--"}%",
                            modifier = GlanceModifier.clickable(actionStartActivity<MainActivity>()),
                            style = TextStyle(
                                color = ColorProvider(textColor),
                                fontSize = 24.sp,
                                fontWeight = FontWeight.Bold
                            )
                        )
                    }

                    Spacer(modifier = GlanceModifier.height(8.dp))

                    // Stepper Controls Row: [-5] [-1] [+1] [+5]
                    Row(
                        modifier = GlanceModifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        StepperButton(text = "-5", delta = -5)
                        Spacer(modifier = GlanceModifier.width(4.dp))
                        StepperButton(text = "-1", delta = -1)
                        Spacer(modifier = GlanceModifier.width(4.dp))
                        StepperButton(text = "+1", delta = 1)
                        Spacer(modifier = GlanceModifier.width(4.dp))
                        StepperButton(text = "+5", delta = 5)
                    }
                }
            } else {
                // Inactive / Disconnected State
                Column(
                    modifier = GlanceModifier.fillMaxSize(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Text(
                        text = "FiiO K17 DAC",
                        style = TextStyle(
                            color = ColorProvider(textColor),
                            fontSize = 15.sp,
                            fontWeight = FontWeight.Bold
                        )
                    )
                    Text(
                        text = "Offline / Disconnected",
                        style = TextStyle(
                            color = ColorProvider(dimText),
                            fontSize = 12.sp
                        )
                    )

                    Spacer(modifier = GlanceModifier.height(8.dp))

                    Box(
                        modifier = GlanceModifier
                            .background(accentColor)
                            .cornerRadius(8.dp)
                            .padding(horizontal = 16.dp, vertical = 6.dp)
                            .clickable(actionRunCallback<ConnectActionCallback>())
                    ) {
                        Text(
                            text = "CONNECT",
                            style = TextStyle(
                                color = ColorProvider(androidx.compose.ui.graphics.Color.Black),
                                fontSize = 13.sp,
                                fontWeight = FontWeight.Bold
                            )
                        )
                    }
                }
            }
        }
    }

    @Composable
    private fun StepperButton(text: String, delta: Int) {
        val buttonBg = androidx.compose.ui.graphics.Color(0xFF2C3246)
        val textColor = androidx.compose.ui.graphics.Color(0xFFFFFFFF)

        Box(
            modifier = GlanceModifier
                .background(buttonBg)
                .cornerRadius(6.dp)
                .padding(horizontal = 10.dp, vertical = 6.dp)
                .clickable(
                    actionRunCallback<AdjustVolumeActionCallback>(
                        actionParametersOf(ActionParameters.Key<Int>("delta") to delta)
                    )
                )
        ) {
            Text(
                text = text,
                style = TextStyle(
                    color = ColorProvider(textColor),
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Bold
                )
            )
        }
    }
}

class ConnectActionCallback : ActionCallback {
    override suspend fun onAction(context: Context, glanceId: GlanceId, parameters: ActionParameters) {
        val backend = K17Backend.getInstance(context)
        backend.fetchStatus()
        K17Widget().update(context, glanceId)
    }
}

class AdjustVolumeActionCallback : ActionCallback {
    override suspend fun onAction(context: Context, glanceId: GlanceId, parameters: ActionParameters) {
        val delta = parameters[ActionParameters.Key<Int>("delta")] ?: 0
        val backend = K17Backend.getInstance(context)
        backend.adjustVolume(delta)
        K17Widget().update(context, glanceId)
    }
}

class CycleModeActionCallback : ActionCallback {
    override suspend fun onAction(context: Context, glanceId: GlanceId, parameters: ActionParameters) {
        val backend = K17Backend.getInstance(context)
        backend.cycleInputMode()
        K17Widget().update(context, glanceId)
    }
}
