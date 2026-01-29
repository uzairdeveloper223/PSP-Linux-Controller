package uzair.ppsspp.linuxcontroller;

import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AlertDialog;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.core.view.WindowInsetsControllerCompat;

import com.google.android.material.switchmaterial.SwitchMaterial;

import java.util.HashMap;
import java.util.Map;

/**
 * Main controller activity with PSP-style layout.
 * Sends button events to Linux server via TCP.
 */
public class MainActivity extends AppCompatActivity implements ConnectionManager.ConnectionListener {

    private ConnectionManager connectionManager;
    private SettingsManager settingsManager;
    private TextView statusText;
    private TextView latencyText;
    private View statusIndicator;
    private Button connectButton;
    private WindowInsetsControllerCompat insetsController;
    
    // Turbo mode
    private Handler turboHandler = new Handler(Looper.getMainLooper());
    private Map<String, Runnable> turboRunnables = new HashMap<>();
    
    // Latency tracking
    private Handler latencyHandler = new Handler(Looper.getMainLooper());
    private Runnable latencyRunnable;
    private long lastPingTime = 0;
    
    // Haptic feedback
    private Vibrator vibrator;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        
        // Keep screen on while using controller
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        
        // Enable edge-to-edge for Android 15+ / Android 16
        WindowCompat.setDecorFitsSystemWindows(getWindow(), false);
        
        setContentView(R.layout.activity_main);
        
        // Setup immersive fullscreen mode
        enableImmersiveMode();
        
        // Initialize managers
        connectionManager = new ConnectionManager(this);
        settingsManager = new SettingsManager(this);
        vibrator = (Vibrator) getSystemService(VIBRATOR_SERVICE);
        
        // Get UI references
        statusText = findViewById(R.id.status_text);
        statusIndicator = findViewById(R.id.status_indicator);
        connectButton = findViewById(R.id.btn_connect);
        latencyText = findViewById(R.id.latency_text);
        
        // Setup buttons
        setupDpad();
        setupActionButtons();
        setupSystemButtons();
        setupShoulderButtons();
        setupAnalogStick();
        
        // Connect button
        connectButton.setOnClickListener(v -> showSettingsDialog());
        
        // Settings button
        findViewById(R.id.btn_settings).setOnClickListener(v -> showSettingsDialog());
        
        updateConnectionStatus(false);
        updateLatencyVisibility();
        
        // Auto-connect if enabled
        if (settingsManager.isAutoConnect() && !connectionManager.getSavedIp().isEmpty()) {
            connectionManager.connect(connectionManager.getSavedIp(), connectionManager.getSavedPort());
        }
    }
    
    /**
     * Enable immersive fullscreen mode using modern WindowInsetsController API.
     */
    private void enableImmersiveMode() {
        View decorView = getWindow().getDecorView();
        insetsController = WindowCompat.getInsetsController(getWindow(), decorView);
        
        if (insetsController != null) {
            insetsController.hide(WindowInsetsCompat.Type.systemBars());
            insetsController.setSystemBarsBehavior(
                WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            );
        }
        
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
            decorView.setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                | View.SYSTEM_UI_FLAG_FULLSCREEN
                | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
            );
        }
    }
    
    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) {
            enableImmersiveMode();
        }
    }
    
    private void showSettingsDialog() {
        View dialogView = getLayoutInflater().inflate(R.layout.dialog_connect, null);
        EditText ipInput = dialogView.findViewById(R.id.input_ip);
        EditText portInput = dialogView.findViewById(R.id.input_port);
        SwitchMaterial turboSwitch = dialogView.findViewById(R.id.switch_turbo);
        SwitchMaterial autoConnectSwitch = dialogView.findViewById(R.id.switch_auto_connect);
        SwitchMaterial showLatencySwitch = dialogView.findViewById(R.id.switch_show_latency);
        SwitchMaterial vibrationSwitch = dialogView.findViewById(R.id.switch_vibration);
        
        // Pre-fill with saved values
        ipInput.setText(connectionManager.getSavedIp());
        portInput.setText(String.valueOf(connectionManager.getSavedPort()));
        turboSwitch.setChecked(settingsManager.isTurboMode());
        autoConnectSwitch.setChecked(settingsManager.isAutoConnect());
        showLatencySwitch.setChecked(settingsManager.isShowLatency());
        vibrationSwitch.setChecked(settingsManager.isVibrationEnabled());
        
        new AlertDialog.Builder(this)
            .setTitle("Settings")
            .setView(dialogView)
            .setPositiveButton("Connect", (dialog, which) -> {
                // Save settings
                settingsManager.setTurboMode(turboSwitch.isChecked());
                settingsManager.setAutoConnect(autoConnectSwitch.isChecked());
                settingsManager.setShowLatency(showLatencySwitch.isChecked());
                settingsManager.setVibrationEnabled(vibrationSwitch.isChecked());
                updateLatencyVisibility();
                
                String ip = ipInput.getText().toString().trim();
                String portStr = portInput.getText().toString().trim();
                
                if (ip.isEmpty()) {
                    Toast.makeText(this, "Please enter IP address", Toast.LENGTH_SHORT).show();
                    return;
                }
                
                int port = 5555;
                try {
                    port = Integer.parseInt(portStr);
                } catch (NumberFormatException e) {
                    // Use default
                }
                
                connectionManager.connect(ip, port);
            })
            .setNegativeButton("Cancel", (dialog, which) -> {
                // Still save settings even if cancelled
                settingsManager.setTurboMode(turboSwitch.isChecked());
                settingsManager.setAutoConnect(autoConnectSwitch.isChecked());
                settingsManager.setShowLatency(showLatencySwitch.isChecked());
                settingsManager.setVibrationEnabled(vibrationSwitch.isChecked());
                updateLatencyVisibility();
            })
            .setNeutralButton("Disconnect", (dialog, which) -> {
                // Save settings first
                settingsManager.setTurboMode(turboSwitch.isChecked());
                settingsManager.setAutoConnect(autoConnectSwitch.isChecked());
                settingsManager.setShowLatency(showLatencySwitch.isChecked());
                settingsManager.setVibrationEnabled(vibrationSwitch.isChecked());
                updateLatencyVisibility();
                connectionManager.disconnect();
            })
            .show();
    }
    
    private void updateLatencyVisibility() {
        if (latencyText != null) {
            latencyText.setVisibility(settingsManager.isShowLatency() ? View.VISIBLE : View.INVISIBLE);
        }
    }
    
    private void setupDpad() {
        setupButton(R.id.btn_dpad_up, "dpad_up");
        setupButton(R.id.btn_dpad_down, "dpad_down");
        setupButton(R.id.btn_dpad_left, "dpad_left");
        setupButton(R.id.btn_dpad_right, "dpad_right");
    }
    
    private void setupActionButtons() {
        setupButton(R.id.btn_x, "x");
        setupButton(R.id.btn_circle, "circle");
        setupButton(R.id.btn_square, "square");
        setupButton(R.id.btn_triangle, "triangle");
    }
    
    private void setupSystemButtons() {
        setupButton(R.id.btn_start, "start");
        setupButton(R.id.btn_select, "select");
    }
    
    private void setupShoulderButtons() {
        setupButton(R.id.btn_l, "l");
        setupButton(R.id.btn_r, "r");
    }
    
    private void setupButton(int viewId, String buttonName) {
        View button = findViewById(viewId);
        if (button != null) {
            button.setOnTouchListener((v, event) -> {
                switch (event.getAction()) {
                    case MotionEvent.ACTION_DOWN:
                        vibrateButton();
                        if (settingsManager.isTurboMode()) {
                            startTurbo(buttonName);
                        } else {
                            connectionManager.sendButtonPress(buttonName);
                        }
                        v.setPressed(true);
                        return true;
                    case MotionEvent.ACTION_UP:
                    case MotionEvent.ACTION_CANCEL:
                        if (settingsManager.isTurboMode()) {
                            stopTurbo(buttonName);
                        } else {
                            connectionManager.sendButtonRelease(buttonName);
                        }
                        v.setPressed(false);
                        return true;
                }
                return false;
            });
        }
    }
    
    private void vibrateButton() {
        if (!settingsManager.isVibrationEnabled()) return;
        
        if (vibrator != null && vibrator.hasVibrator()) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                vibrator.vibrate(VibrationEffect.createOneShot(10, VibrationEffect.DEFAULT_AMPLITUDE));
            } else {
                vibrator.vibrate(10);
            }
        }
    }
    
    private void startTurbo(String buttonName) {
        // Stop any existing turbo for this button
        stopTurbo(buttonName);
        
        int interval = settingsManager.getTurboInterval();
        
        Runnable turboRunnable = new Runnable() {
            @Override
            public void run() {
                connectionManager.sendButtonPress(buttonName);
                turboHandler.postDelayed(() -> {
                    connectionManager.sendButtonRelease(buttonName);
                }, interval / 2);
                turboHandler.postDelayed(this, interval);
            }
        };
        
        turboRunnables.put(buttonName, turboRunnable);
        turboHandler.post(turboRunnable);
    }
    
    private void stopTurbo(String buttonName) {
        Runnable runnable = turboRunnables.remove(buttonName);
        if (runnable != null) {
            turboHandler.removeCallbacks(runnable);
            connectionManager.sendButtonRelease(buttonName);
        }
    }
    
    private void setupAnalogStick() {
        View analogArea = findViewById(R.id.analog_area);
        View analogStick = findViewById(R.id.analog_stick);
        
        if (analogArea != null && analogStick != null) {
            analogArea.setOnTouchListener((v, event) -> {
                float centerX = v.getWidth() / 2f;
                float centerY = v.getHeight() / 2f;
                float maxRadius = Math.min(centerX, centerY) * 0.8f;
                
                switch (event.getAction()) {
                    case MotionEvent.ACTION_DOWN:
                    case MotionEvent.ACTION_MOVE:
                        float dx = event.getX() - centerX;
                        float dy = event.getY() - centerY;
                        
                        float distance = (float) Math.sqrt(dx * dx + dy * dy);
                        if (distance > maxRadius) {
                            dx = dx * maxRadius / distance;
                            dy = dy * maxRadius / distance;
                        }
                        
                        analogStick.setTranslationX(dx);
                        analogStick.setTranslationY(dy);
                        
                        float normalX = dx / maxRadius;
                        float normalY = dy / maxRadius;
                        
                        connectionManager.sendAnalog(normalX, normalY);
                        return true;
                        
                    case MotionEvent.ACTION_UP:
                    case MotionEvent.ACTION_CANCEL:
                        analogStick.setTranslationX(0);
                        analogStick.setTranslationY(0);
                        connectionManager.sendAnalog(0, 0);
                        return true;
                }
                return false;
            });
        }
    }
    
    private void startLatencyMonitor() {
        if (latencyRunnable != null) {
            latencyHandler.removeCallbacks(latencyRunnable);
        }
        
        latencyRunnable = new Runnable() {
            @Override
            public void run() {
                if (connectionManager.isConnected()) {
                    lastPingTime = System.currentTimeMillis();
                    connectionManager.sendPing();
                }
                latencyHandler.postDelayed(this, 1000); // Check every second
            }
        };
        latencyHandler.post(latencyRunnable);
    }
    
    private void stopLatencyMonitor() {
        if (latencyRunnable != null) {
            latencyHandler.removeCallbacks(latencyRunnable);
            latencyRunnable = null;
        }
    }
    
    @Override
    public void onConnected() {
        runOnUiThread(() -> {
            updateConnectionStatus(true);
            Toast.makeText(this, "Connected!", Toast.LENGTH_SHORT).show();
            startLatencyMonitor();
        });
    }
    
    @Override
    public void onDisconnected() {
        runOnUiThread(() -> {
            updateConnectionStatus(false);
            stopLatencyMonitor();
        });
    }
    
    @Override
    public void onConnectionError(String message) {
        runOnUiThread(() -> {
            updateConnectionStatus(false);
            Toast.makeText(this, "Error: " + message, Toast.LENGTH_LONG).show();
            stopLatencyMonitor();
        });
    }
    
    @Override
    public void onLatencyUpdate(long latencyMs) {
        runOnUiThread(() -> {
            if (latencyText != null && settingsManager.isShowLatency()) {
                latencyText.setText(latencyMs + " ms");
                
                // Color based on latency
                if (latencyMs < 20) {
                    latencyText.setTextColor(0xFF4CAF50); // Green
                } else if (latencyMs < 50) {
                    latencyText.setTextColor(0xFFFFEB3B); // Yellow
                } else {
                    latencyText.setTextColor(0xFFF44336); // Red
                }
            }
        });
    }
    
    private void updateConnectionStatus(boolean connected) {
        if (connected) {
            statusText.setText("Connected");
            statusText.setTextColor(0xFF4CAF50); // Green
            statusIndicator.setBackgroundResource(R.drawable.status_connected);
            connectButton.setText("Connected ●");
        } else {
            statusText.setText("Disconnected");
            statusText.setTextColor(0xFFE94560); // Red/Pink
            statusIndicator.setBackgroundResource(R.drawable.status_disconnected);
            connectButton.setText("Connect");
            if (latencyText != null) {
                latencyText.setText("-- ms");
            }
        }
    }
    
    @Override
    protected void onDestroy() {
        super.onDestroy();
        stopLatencyMonitor();
        // Stop all turbo buttons
        for (String button : turboRunnables.keySet()) {
            stopTurbo(button);
        }
        if (connectionManager != null) {
            connectionManager.disconnect();
        }
    }
}
