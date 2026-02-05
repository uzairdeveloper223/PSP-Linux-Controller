package uzair.ppsspp.linuxcontroller;

import android.content.Intent;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.Spinner;
import android.widget.TextView;
import android.widget.Toast;
import android.webkit.WebView;
import android.webkit.WebSettings;

import androidx.appcompat.app.AlertDialog;
import androidx.appcompat.app.AppCompatActivity;
import androidx.appcompat.app.AppCompatDelegate;
import androidx.activity.result.ActivityResultLauncher;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.core.view.WindowInsetsControllerCompat;

import com.google.android.material.switchmaterial.SwitchMaterial;
import com.journeyapps.barcodescanner.ScanContract;
import com.journeyapps.barcodescanner.ScanOptions;

import java.util.HashMap;
import java.util.Map;

/**
 * Main controller activity with PSP-style layout.
 * Sends button events to Linux server via TCP.
 */
public class MainActivity extends AppCompatActivity implements ConnectionManager.ConnectionListener {

    private ConnectionManager connectionManager;
    private SettingsManager settingsManager;
    private LayoutSettingsManager layoutSettingsManager;
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
    
    // Connection dialog reference
    private AlertDialog connectionDialog;
    
    // Stream view
    private WebView streamView;
    private boolean isStreaming = false;
    
    // QR Code scanner
    private final ActivityResultLauncher<ScanOptions> barcodeLauncher = registerForActivityResult(new ScanContract(),
        result -> {
            if (result.getContents() != null) {
                // Parse the QR code content (should be in format "ip:port")
                String qrContent = result.getContents();
                String[] parts = qrContent.split(":");

                if (parts.length == 2) {
                    String ip = parts[0];
                    String portStr = parts[1];

                    try {
                        int port = Integer.parseInt(portStr);
                        connectionManager.connect(ip, port);
                        Toast.makeText(this, "Connecting to " + ip + ":" + port, Toast.LENGTH_LONG).show();
                        
                        // Close the connection dialog after successful scan
                        if (connectionDialog != null && connectionDialog.isShowing()) {
                            connectionDialog.dismiss();
                        }
                    } catch (NumberFormatException e) {
                        Toast.makeText(this, "Invalid port in QR code: " + portStr, Toast.LENGTH_LONG).show();
                    }
                } else {
                    Toast.makeText(this, "Invalid QR code format. Expected: ip:port", Toast.LENGTH_LONG).show();
                }
            }
        });

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        // Apply dark mode before super.onCreate
        // Need to initialize settings early for dark mode
        SettingsManager tempSettings = new SettingsManager(this);
        if (tempSettings.isDarkMode()) {
            AppCompatDelegate.setDefaultNightMode(AppCompatDelegate.MODE_NIGHT_YES);
        } else {
            AppCompatDelegate.setDefaultNightMode(AppCompatDelegate.MODE_NIGHT_NO);
        }
        
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
        settingsManager = tempSettings;
        layoutSettingsManager = new LayoutSettingsManager(this);
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
        
        // Apply custom layout positions
        applyCustomLayout();
        
        // Connect button opens connection dialog
        connectButton.setOnClickListener(v -> showConnectionDialog());
        
        // Settings button opens settings dialog
        findViewById(R.id.btn_settings).setOnClickListener(v -> showSettingsDialog());
        
        // Setup top bar toggle
        setupTopBarToggle();
        
        updateConnectionStatus(false);
        updateLatencyVisibility();
        updateTopBarVisibility();
        
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
    
    private void showConnectionDialog() {
        View dialogView = getLayoutInflater().inflate(R.layout.dialog_connection, null);
        EditText ipInput = dialogView.findViewById(R.id.input_ip);
        EditText portInput = dialogView.findViewById(R.id.input_port);
        Button scanQrButton = dialogView.findViewById(R.id.btn_scan_qr);
        View dialogRoot = dialogView.findViewById(R.id.dialog_root);

        // Pre-fill with saved values
        ipInput.setText(connectionManager.getSavedIp());
        portInput.setText(String.valueOf(connectionManager.getSavedPort()));

        // Apply background based on dark mode
        if (settingsManager.isDarkMode()) {
            dialogRoot.setBackgroundColor(0xFF1a1a2e);
        } else {
            dialogRoot.setBackgroundColor(0xFFFFFFFF);
        }

        AlertDialog dialog = new AlertDialog.Builder(this)
            .setTitle("Connect")
            .setView(dialogView)
            .setPositiveButton("Connect", (d, which) -> {
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
            .setNegativeButton("Cancel", null)
            .setNeutralButton("Disconnect", (d, which) -> {
                connectionManager.disconnect();
            })
            .create();

        connectionDialog = dialog;  // Store reference
        dialog.show();

        // Set button text colors based on dark mode
        if (settingsManager.isDarkMode()) {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setTextColor(0xFFFFFFFF);
            dialog.getButton(AlertDialog.BUTTON_NEGATIVE).setTextColor(0xFFFFFFFF);
            dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setTextColor(0xFFFFFFFF);
        }

        // Set up QR code scanning
        scanQrButton.setOnClickListener(v -> {
            ScanOptions options = new ScanOptions();
            options.setDesiredBarcodeFormats(ScanOptions.QR_CODE);
            options.setPrompt("Scan QR Code to connect to server");
            options.setCameraId(0);
            options.setBeepEnabled(false);
            options.setBarcodeImageEnabled(true);
            barcodeLauncher.launch(options);
        });
    }
    
    private void showSettingsDialog() {
        View dialogView = getLayoutInflater().inflate(R.layout.dialog_settings, null);
        SwitchMaterial turboSwitch = dialogView.findViewById(R.id.switch_turbo);
        SwitchMaterial autoConnectSwitch = dialogView.findViewById(R.id.switch_auto_connect);
        SwitchMaterial showLatencySwitch = dialogView.findViewById(R.id.switch_show_latency);
        SwitchMaterial vibrationSwitch = dialogView.findViewById(R.id.switch_vibration);
        SwitchMaterial darkModeSwitch = dialogView.findViewById(R.id.switch_dark_mode);
        SwitchMaterial gameStreamSwitch = dialogView.findViewById(R.id.switch_game_stream);
        View dialogRoot = dialogView.findViewById(R.id.dialog_root);
        
        // Layout customization controls
        Spinner presetSpinner = dialogView.findViewById(R.id.spinner_preset);
        Button btnResetLayout = dialogView.findViewById(R.id.btn_reset_layout);
        
        // Pre-fill with saved values
        turboSwitch.setChecked(settingsManager.isTurboMode());
        autoConnectSwitch.setChecked(settingsManager.isAutoConnect());
        showLatencySwitch.setChecked(settingsManager.isShowLatency());
        vibrationSwitch.setChecked(settingsManager.isVibrationEnabled());
        darkModeSwitch.setChecked(settingsManager.isDarkMode());
        gameStreamSwitch.setChecked(settingsManager.isGameStreamEnabled());
        
        // Apply background based on dark mode
        if (settingsManager.isDarkMode()) {
            dialogRoot.setBackgroundColor(0xFF1a1a2e);
        } else {
            dialogRoot.setBackgroundColor(0xFFFFFFFF);
        }
        
        // Dark mode toggle - save and show toast
        darkModeSwitch.setOnCheckedChangeListener((buttonView, isChecked) -> {
            settingsManager.setDarkMode(isChecked);
            applyDarkMode();
            String message = isChecked ? "Dark Mode: On" : "Dark Mode: Off";
            Toast.makeText(MainActivity.this, message, Toast.LENGTH_SHORT).show();
        });
        
        // Game stream toggle - start/stop streaming immediately
        gameStreamSwitch.setOnCheckedChangeListener((buttonView, isChecked) -> {
            settingsManager.setGameStreamEnabled(isChecked);
            if (isChecked) {
                if (connectionManager != null && connectionManager.isConnected()) {
                    requestGameStream();
                    Toast.makeText(MainActivity.this, "Starting game stream...", Toast.LENGTH_SHORT).show();
                } else {
                    Toast.makeText(MainActivity.this, "Connect to server first", Toast.LENGTH_SHORT).show();
                    gameStreamSwitch.setChecked(false);
                    settingsManager.setGameStreamEnabled(false);
                }
            } else {
                if (connectionManager != null) {
                    connectionManager.stopStream();
                }
                stopGameStream();
                Toast.makeText(MainActivity.this, "Stream stopped", Toast.LENGTH_SHORT).show();
            }
        });
        
        // Setup preset spinner
        String[] presets = {"Default", "Compact", "Wide", "Custom"};
        ArrayAdapter<String> adapter = new ArrayAdapter<>(this, 
            android.R.layout.simple_spinner_item, presets);
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        presetSpinner.setAdapter(adapter);
        
        // Set current preset selection
        String currentPreset = layoutSettingsManager.getLayoutPreset();
        int presetIndex = 0;
        switch (currentPreset) {
            case LayoutSettingsManager.PRESET_COMPACT: presetIndex = 1; break;
            case LayoutSettingsManager.PRESET_WIDE: presetIndex = 2; break;
            case LayoutSettingsManager.PRESET_CUSTOM: presetIndex = 3; break;
        }
        presetSpinner.setSelection(presetIndex);
        
        // Preset spinner listener
        presetSpinner.setOnItemSelectedListener(new android.widget.AdapterView.OnItemSelectedListener() {
            @Override
            public void onItemSelected(android.widget.AdapterView<?> parent, View view, int position, long id) {
                String[] presetValues = {
                    LayoutSettingsManager.PRESET_DEFAULT,
                    LayoutSettingsManager.PRESET_COMPACT,
                    LayoutSettingsManager.PRESET_WIDE,
                    LayoutSettingsManager.PRESET_CUSTOM
                };
                if (position < 3) { // Don't apply custom preset from spinner
                    layoutSettingsManager.applyPreset(presetValues[position]);
                    applyCustomLayout();
                }
            }
            @Override
            public void onNothingSelected(android.widget.AdapterView<?> parent) {}
        });
        
        // Reset Layout button
        btnResetLayout.setOnClickListener(v -> {
            new AlertDialog.Builder(MainActivity.this)
                .setTitle("Reset Layout")
                .setMessage("Reset all controls to default positions?")
                .setPositiveButton("Reset", (d, w) -> {
                    layoutSettingsManager.resetAll();
                    applyCustomLayout();
                    presetSpinner.setSelection(0);
                    Toast.makeText(MainActivity.this, "Layout reset to default", Toast.LENGTH_SHORT).show();
                })
                .setNegativeButton("Cancel", null)
                .show();
        });
        
        AlertDialog dialog = new AlertDialog.Builder(this)
            .setTitle("Settings")
            .setView(dialogView)
            .setPositiveButton("OK", (d, which) -> {
                // Save settings
                settingsManager.setTurboMode(turboSwitch.isChecked());
                settingsManager.setAutoConnect(autoConnectSwitch.isChecked());
                settingsManager.setShowLatency(showLatencySwitch.isChecked());
                settingsManager.setVibrationEnabled(vibrationSwitch.isChecked());
                settingsManager.setDarkMode(darkModeSwitch.isChecked());
                applyDarkMode();
                updateLatencyVisibility();
            })
            .setNegativeButton("Cancel", null)
            .create();
        
        dialog.show();
        
        // Set button text colors based on dark mode
        if (settingsManager.isDarkMode()) {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setTextColor(0xFFFFFFFF);
            dialog.getButton(AlertDialog.BUTTON_NEGATIVE).setTextColor(0xFFFFFFFF);
        }
    }
    
    private void applyDarkMode() {
        if (settingsManager.isDarkMode()) {
            AppCompatDelegate.setDefaultNightMode(AppCompatDelegate.MODE_NIGHT_YES);
        } else {
            AppCompatDelegate.setDefaultNightMode(AppCompatDelegate.MODE_NIGHT_NO);
        }
    }
    
    private void updateLatencyVisibility() {
        if (latencyText != null) {
            latencyText.setVisibility(settingsManager.isShowLatency() ? View.VISIBLE : View.INVISIBLE);
        }
    }
    
    private void setupTopBarToggle() {
        View topBar = findViewById(R.id.top_bar);
        View btnToggleBar = findViewById(R.id.btn_toggle_bar);
        View btnShowBar = findViewById(R.id.btn_show_bar);
        
        if (btnToggleBar != null) {
            btnToggleBar.setOnClickListener(v -> {
                // Hide the top bar
                layoutSettingsManager.setTopBarVisible(false);
                updateTopBarVisibility();
            });
        }
        
        if (btnShowBar != null) {
            btnShowBar.setOnClickListener(v -> {
                // Show the top bar
                layoutSettingsManager.setTopBarVisible(true);
                updateTopBarVisibility();
            });
        }
    }
    
    private void updateTopBarVisibility() {
        View topBar = findViewById(R.id.top_bar);
        View btnShowBar = findViewById(R.id.btn_show_bar);
        
        if (layoutSettingsManager == null) return;
        
        boolean isVisible = layoutSettingsManager.isTopBarVisible();
        
        if (topBar != null) {
            topBar.setVisibility(isVisible ? View.VISIBLE : View.GONE);
        }
        
        if (btnShowBar != null) {
            btnShowBar.setVisibility(isVisible ? View.GONE : View.VISIBLE);
        }
    }
    
    /**
     * Apply custom layout positions, scales, opacity, and visibility to controls.
     */
    private void applyCustomLayout() {
        // Get the controller canvas
        FrameLayout canvas = findViewById(R.id.controller_canvas);
        if (canvas == null) return;
        
        // Apply layout after views are measured
        canvas.post(() -> {
            int canvasWidth = canvas.getWidth();
            int canvasHeight = canvas.getHeight();
            
            // D-Pad container
            applyControlLayout(findViewById(R.id.dpad_container), 
                LayoutSettingsManager.CONTROL_DPAD, canvasWidth, canvasHeight);
            
            // Analog area
            applyControlLayout(findViewById(R.id.analog_area), 
                LayoutSettingsManager.CONTROL_ANALOG, canvasWidth, canvasHeight);
            
            // Action buttons container
            applyControlLayout(findViewById(R.id.action_container), 
                LayoutSettingsManager.CONTROL_ACTION_BUTTONS, canvasWidth, canvasHeight);
            
            // L Button
            applyControlLayout(findViewById(R.id.btn_l), 
                LayoutSettingsManager.CONTROL_L_BUTTON, canvasWidth, canvasHeight);
            
            // R Button
            applyControlLayout(findViewById(R.id.btn_r), 
                LayoutSettingsManager.CONTROL_R_BUTTON, canvasWidth, canvasHeight);
            
            // Start Button
            applyControlLayout(findViewById(R.id.btn_start), 
                LayoutSettingsManager.CONTROL_START, canvasWidth, canvasHeight);
            
            // Select Button
            applyControlLayout(findViewById(R.id.btn_select), 
                LayoutSettingsManager.CONTROL_SELECT, canvasWidth, canvasHeight);
        });
    }
    
    private void applyControlLayout(View view, String controlId, int canvasWidth, int canvasHeight) {
        if (view == null || layoutSettingsManager == null) return;
        
        LayoutSettingsManager.ControlSettings settings = layoutSettingsManager.getControlSettings(controlId);
        
        // Apply position (X and Y as percentages of canvas)
        float posX = settings.posX * canvasWidth;
        float posY = settings.posY * canvasHeight;
        view.setX(posX);
        view.setY(posY);
        
        // Apply scale
        view.setScaleX(settings.scale);
        view.setScaleY(settings.scale);
        
        // Apply opacity
        view.setAlpha(settings.opacity);
        
        // Apply visibility
        view.setVisibility(settings.visible ? View.VISIBLE : View.INVISIBLE);
    }
    
    @Override
    protected void onResume() {
        super.onResume();
        // Reapply layout when returning from layout editor
        if (layoutSettingsManager != null) {
            applyCustomLayout();
        }
        // Restore top bar visibility state
        updateTopBarVisibility();
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
                vibrator.vibrate(VibrationEffect.createOneShot(30, VibrationEffect.DEFAULT_AMPLITUDE));
            } else {
                vibrator.vibrate(30);
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
                float maxRadius = Math.min(centerX, centerY) * 0.7f;
                
                int action = event.getActionMasked();
                
                if (action == MotionEvent.ACTION_DOWN || action == MotionEvent.ACTION_MOVE) {
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
                } else if (action == MotionEvent.ACTION_UP || 
                           action == MotionEvent.ACTION_CANCEL || 
                           action == MotionEvent.ACTION_OUTSIDE ||
                           action == MotionEvent.ACTION_POINTER_UP) {
                    // Reset stick position and send zero input
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
            // Send current layout to server for Layout Editor
            if (connectionManager != null && layoutSettingsManager != null) {
                connectionManager.sendCurrentLayout(layoutSettingsManager);
            }
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
    
    @Override
    public void onLayoutPreview(String controlId, float x, float y, float scale, float opacity, boolean visible) {
        runOnUiThread(() -> {
            // Find the control view
            View controlView = getControlView(controlId);
            if (controlView == null) return;
            
            FrameLayout canvas = findViewById(R.id.controller_canvas);
            if (canvas == null) return;
            
            int canvasWidth = canvas.getWidth();
            int canvasHeight = canvas.getHeight();
            
            // Apply live preview changes (only apply values that were sent)
            if (x >= 0 && x <= 1) {
                controlView.setX(x * canvasWidth);
            }
            if (y >= 0 && y <= 1) {
                controlView.setY(y * canvasHeight);
            }
            if (scale > 0) {
                controlView.setScaleX(scale);
                controlView.setScaleY(scale);
            }
            if (opacity >= 0 && opacity <= 1) {
                controlView.setAlpha(opacity);
            }
            controlView.setVisibility(visible ? View.VISIBLE : View.INVISIBLE);
        });
    }
    
    @Override
    public void onSetLayout(String layoutJson) {
        runOnUiThread(() -> {
            // Parse and save the layout from desktop editor
            try {
                org.json.JSONObject layout = new org.json.JSONObject(layoutJson);
                java.util.Iterator<String> keys = layout.keys();
                
                while (keys.hasNext()) {
                    String controlId = keys.next();
                    org.json.JSONObject settings = layout.getJSONObject(controlId);
                    
                    float posX = (float) settings.optDouble("x", 0.5);
                    float posY = (float) settings.optDouble("y", 0.5);
                    float scale = (float) settings.optDouble("scale", 1.0);
                    float opacity = (float) settings.optDouble("opacity", 1.0);
                    boolean visible = settings.optBoolean("visible", true);
                    
                    // Save to layout settings manager
                    layoutSettingsManager.setPosition(controlId, posX, posY);
                    layoutSettingsManager.setScale(controlId, scale);
                    layoutSettingsManager.setOpacity(controlId, opacity);
                    layoutSettingsManager.setVisible(controlId, visible);
                }
                
                // Apply the saved layout
                applyCustomLayout();
                Toast.makeText(this, "Layout saved from desktop editor", Toast.LENGTH_SHORT).show();
                
            } catch (org.json.JSONException e) {
                e.printStackTrace();
            }
        });
    }
    
    /**
     * Get the control view by control ID.
     */
    private View getControlView(String controlId) {
        switch (controlId) {
            case LayoutSettingsManager.CONTROL_DPAD:
                return findViewById(R.id.dpad_container);
            case LayoutSettingsManager.CONTROL_ANALOG:
                return findViewById(R.id.analog_area);
            case LayoutSettingsManager.CONTROL_ACTION_BUTTONS:
                return findViewById(R.id.action_container);
            case LayoutSettingsManager.CONTROL_L_BUTTON:
                return findViewById(R.id.btn_l);
            case LayoutSettingsManager.CONTROL_R_BUTTON:
                return findViewById(R.id.btn_r);
            case LayoutSettingsManager.CONTROL_START:
                return findViewById(R.id.btn_start);
            case LayoutSettingsManager.CONTROL_SELECT:
                return findViewById(R.id.btn_select);
            default:
                return null;
        }
    }
    
    private void updateConnectionStatus(boolean connected) {
        if (connected) {
            statusText.setText("Connected");
            statusText.setTextColor(0xFF4CAF50); // Green
            statusIndicator.setBackgroundResource(R.drawable.status_connected);
            connectButton.setText("Connected +");
        } else {
            statusText.setText("Disconnected");
            statusText.setTextColor(0xFFE94560); // Red/Pink
            statusIndicator.setBackgroundResource(R.drawable.status_disconnected);
            connectButton.setText("Connect");
            if (latencyText != null) {
                latencyText.setText("-- ms");
            }
            // Stop streaming when disconnected
            if (isStreaming) {
                stopGameStream();
            }
        }
    }
    
    // Stream callback implementations
    
    @Override
    public void onStreamStart(String url, int port, int width, int height) {
        runOnUiThread(() -> {
            startGameStream(url);
        });
    }
    
    @Override
    public void onStreamStop() {
        runOnUiThread(() -> {
            stopGameStream();
        });
    }
    
    @Override
    public void onStreamError(String message) {
        runOnUiThread(() -> {
            Toast.makeText(this, "Stream error: " + message, Toast.LENGTH_SHORT).show();
            stopGameStream();
        });
    }
    
    /**
     * Start displaying the game stream in background.
     */
    private void startGameStream(String streamUrl) {
        if (streamView == null) {
            streamView = findViewById(R.id.stream_view);
        }
        
        if (streamView != null) {
            android.util.Log.d("PSPController", "Starting stream from: " + streamUrl);
            
            // Configure WebView for MJPEG stream
            WebSettings webSettings = streamView.getSettings();
            webSettings.setJavaScriptEnabled(true);
            webSettings.setLoadWithOverviewMode(true);
            webSettings.setUseWideViewPort(true);
            webSettings.setBuiltInZoomControls(false);
            webSettings.setDisplayZoomControls(false);
            webSettings.setCacheMode(WebSettings.LOAD_NO_CACHE);
            webSettings.setDomStorageEnabled(true);
            webSettings.setMediaPlaybackRequiresUserGesture(false);
            
            // Allow mixed content for HTTP stream
            webSettings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
            
            // Load the MJPEG stream directly - img tag works for MJPEG
            String html = "<!DOCTYPE html><html><head><meta name='viewport' content='width=device-width, initial-scale=1.0'>"
                    + "<style>*{margin:0;padding:0}body{background:#000;overflow:hidden}"
                    + "img{width:100vw;height:100vh;object-fit:cover}</style></head>"
                    + "<body><img src='" + streamUrl + "' alt='stream'/></body></html>";
            
            streamView.loadDataWithBaseURL("http://localhost/", html, "text/html", "UTF-8", null);
            streamView.setVisibility(View.VISIBLE);
            isStreaming = true;
            
            // Make controller canvas transparent and buttons semi-transparent
            View controllerCanvas = findViewById(R.id.controller_canvas);
            if (controllerCanvas != null) {
                controllerCanvas.setBackgroundColor(0x00000000); // Fully transparent
                // Make all child controls semi-transparent
                setControlsTransparency(0.5f);
            }
            
            // Hide the dark background
            View rootLayout = findViewById(R.id.root_layout);
            if (rootLayout != null) {
                rootLayout.setBackgroundColor(0xFF000000); // Pure black for stream
            }
        } else {
            android.util.Log.e("PSPController", "streamView is null!");
        }
    }
    
    /**
     * Stop the game stream display.
     */
    private void stopGameStream() {
        if (streamView != null) {
            streamView.loadUrl("about:blank");
            streamView.setVisibility(View.GONE);
        }
        isStreaming = false;
        settingsManager.setGameStreamEnabled(false);
        
        // Restore controller transparency
        setControlsTransparency(1.0f);
        
        // Restore background color
        View rootLayout = findViewById(R.id.root_layout);
        if (rootLayout != null) {
            rootLayout.setBackgroundColor(0xFF1a1a2e); // Original dark purple
        }
    }
    
    /**
     * Set transparency for all controller buttons.
     */
    private void setControlsTransparency(float alpha) {
        int[] controlIds = {
            R.id.dpad_container,
            R.id.analog_area,
            R.id.action_container,
            R.id.btn_l,
            R.id.btn_r,
            R.id.btn_start,
            R.id.btn_select
        };
        
        for (int id : controlIds) {
            View control = findViewById(id);
            if (control != null) {
                control.setAlpha(alpha);
            }
        }
    }
    
    /**
     * Request game stream from server.
     */
    private void requestGameStream() {
        if (connectionManager != null && connectionManager.isConnected()) {
            android.util.DisplayMetrics metrics = getResources().getDisplayMetrics();
            connectionManager.requestStream(metrics.widthPixels, metrics.heightPixels);
        }
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        stopLatencyMonitor();
        // Stop streaming
        if (connectionManager != null && isStreaming) {
            connectionManager.stopStream();
        }
        // Stop all turbo buttons
        for (String button : turboRunnables.keySet()) {
            stopTurbo(button);
        }
        if (connectionManager != null) {
            connectionManager.disconnect();
        }
    }
}
