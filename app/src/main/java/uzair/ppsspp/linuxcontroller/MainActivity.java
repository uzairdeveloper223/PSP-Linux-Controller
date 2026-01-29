package uzair.ppsspp.linuxcontroller;

import android.os.Build;
import android.os.Bundle;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageButton;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AlertDialog;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.core.view.WindowInsetsControllerCompat;

/**
 * Main controller activity with PSP-style layout.
 * Sends button events to Linux server via TCP.
 */
public class MainActivity extends AppCompatActivity implements ConnectionManager.ConnectionListener {

    private ConnectionManager connectionManager;
    private TextView statusText;
    private View statusIndicator;
    private Button connectButton;
    private WindowInsetsControllerCompat insetsController;

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
        
        // Initialize connection manager
        connectionManager = new ConnectionManager(this);
        
        // Get UI references
        statusText = findViewById(R.id.status_text);
        statusIndicator = findViewById(R.id.status_indicator);
        connectButton = findViewById(R.id.btn_connect);
        
        // Setup buttons
        setupDpad();
        setupActionButtons();
        setupSystemButtons();
        setupShoulderButtons();
        setupAnalogStick();
        
        // Connect button
        connectButton.setOnClickListener(v -> showConnectionDialog());
        
        // Settings button
        findViewById(R.id.btn_settings).setOnClickListener(v -> showConnectionDialog());
        
        updateConnectionStatus(false);
    }
    
    /**
     * Enable immersive fullscreen mode using modern WindowInsetsController API.
     * Hides status bar, navigation bar, and handles edge-to-edge for Android 16.
     */
    private void enableImmersiveMode() {
        View decorView = getWindow().getDecorView();
        insetsController = WindowCompat.getInsetsController(getWindow(), decorView);
        
        if (insetsController != null) {
            // Hide both status bar and navigation bar
            insetsController.hide(WindowInsetsCompat.Type.systemBars());
            
            // Allow bars to appear temporarily with swipe, then auto-hide
            insetsController.setSystemBarsBehavior(
                WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            );
        }
        
        // Legacy flags for older Android versions
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
        // Re-enable immersive mode when window regains focus
        if (hasFocus) {
            enableImmersiveMode();
        }
    }
    
    private void showConnectionDialog() {
        View dialogView = getLayoutInflater().inflate(R.layout.dialog_connect, null);
        EditText ipInput = dialogView.findViewById(R.id.input_ip);
        EditText portInput = dialogView.findViewById(R.id.input_port);
        
        // Pre-fill with saved values
        ipInput.setText(connectionManager.getSavedIp());
        portInput.setText(String.valueOf(connectionManager.getSavedPort()));
        
        new AlertDialog.Builder(this)
            .setTitle("Connect to Server")
            .setView(dialogView)
            .setPositiveButton("Connect", (dialog, which) -> {
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
            .setNeutralButton("Disconnect", (dialog, which) -> {
                connectionManager.disconnect();
            })
            .show();
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
                        connectionManager.sendButtonPress(buttonName);
                        v.setPressed(true);
                        return true;
                    case MotionEvent.ACTION_UP:
                    case MotionEvent.ACTION_CANCEL:
                        connectionManager.sendButtonRelease(buttonName);
                        v.setPressed(false);
                        return true;
                }
                return false;
            });
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
                        
                        // Clamp to max radius
                        float distance = (float) Math.sqrt(dx * dx + dy * dy);
                        if (distance > maxRadius) {
                            dx = dx * maxRadius / distance;
                            dy = dy * maxRadius / distance;
                        }
                        
                        // Move analog stick visual
                        analogStick.setTranslationX(dx);
                        analogStick.setTranslationY(dy);
                        
                        // Normalize to -1 to 1
                        float normalX = dx / maxRadius;
                        float normalY = dy / maxRadius;
                        
                        connectionManager.sendAnalog(normalX, normalY);
                        return true;
                        
                    case MotionEvent.ACTION_UP:
                    case MotionEvent.ACTION_CANCEL:
                        // Reset to center
                        analogStick.setTranslationX(0);
                        analogStick.setTranslationY(0);
                        connectionManager.sendAnalog(0, 0);
                        return true;
                }
                return false;
            });
        }
    }
    
    @Override
    public void onConnected() {
        runOnUiThread(() -> {
            updateConnectionStatus(true);
            Toast.makeText(this, "Connected!", Toast.LENGTH_SHORT).show();
        });
    }
    
    @Override
    public void onDisconnected() {
        runOnUiThread(() -> {
            updateConnectionStatus(false);
        });
    }
    
    @Override
    public void onConnectionError(String message) {
        runOnUiThread(() -> {
            updateConnectionStatus(false);
            Toast.makeText(this, "Error: " + message, Toast.LENGTH_LONG).show();
        });
    }
    
    private void updateConnectionStatus(boolean connected) {
        if (connected) {
            statusText.setText("Connected");
            statusIndicator.setBackgroundResource(R.drawable.status_connected);
            connectButton.setText("Connected ●");
        } else {
            statusText.setText("Disconnected");
            statusIndicator.setBackgroundResource(R.drawable.status_disconnected);
            connectButton.setText("Connect");
        }
    }
    
    @Override
    protected void onDestroy() {
        super.onDestroy();
        if (connectionManager != null) {
            connectionManager.disconnect();
        }
    }
}
