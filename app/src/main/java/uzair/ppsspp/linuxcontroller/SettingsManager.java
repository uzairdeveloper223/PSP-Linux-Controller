package uzair.ppsspp.linuxcontroller;

import android.content.Context;
import android.content.SharedPreferences;

/**
 * Manages app settings/preferences.
 */
public class SettingsManager {
    
    private static final String PREFS_NAME = "psp_controller_prefs";
    
    // Setting keys
    private static final String PREF_TURBO_MODE = "turbo_mode";
    private static final String PREF_AUTO_CONNECT = "auto_connect";
    private static final String PREF_SHOW_LATENCY = "show_latency";
    private static final String PREF_TURBO_INTERVAL = "turbo_interval";
    
    private SharedPreferences prefs;
    
    public SettingsManager(Context context) {
        this.prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
    }
    
    // Turbo Mode
    public boolean isTurboMode() {
        return prefs.getBoolean(PREF_TURBO_MODE, false);
    }
    
    public void setTurboMode(boolean enabled) {
        prefs.edit().putBoolean(PREF_TURBO_MODE, enabled).apply();
    }
    
    // Auto Connect
    public boolean isAutoConnect() {
        return prefs.getBoolean(PREF_AUTO_CONNECT, false);
    }
    
    public void setAutoConnect(boolean enabled) {
        prefs.edit().putBoolean(PREF_AUTO_CONNECT, enabled).apply();
    }
    
    // Show Latency
    public boolean isShowLatency() {
        return prefs.getBoolean(PREF_SHOW_LATENCY, true);
    }
    
    public void setShowLatency(boolean enabled) {
        prefs.edit().putBoolean(PREF_SHOW_LATENCY, enabled).apply();
    }
    
    // Turbo interval in milliseconds
    public int getTurboInterval() {
        return prefs.getInt(PREF_TURBO_INTERVAL, 50); // 50ms = 20 presses/sec
    }
    
    public void setTurboInterval(int intervalMs) {
        prefs.edit().putInt(PREF_TURBO_INTERVAL, intervalMs).apply();
    }
    
    // Vibration
    public boolean isVibrationEnabled() {
        return prefs.getBoolean("vibration_enabled", true);
    }
    
    public void setVibrationEnabled(boolean enabled) {
        prefs.edit().putBoolean("vibration_enabled", enabled).apply();
    }
}
