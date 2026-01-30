package uzair.ppsspp.linuxcontroller;

import android.content.Context;
import android.content.SharedPreferences;

/**
 * Manages layout customization settings for all controller elements.
 * Stores positions as percentages of screen dimensions for cross-device compatibility.
 */
public class LayoutSettingsManager {
    
    private static final String PREFS_NAME = "psp_layout_prefs";
    
    // Control identifiers
    public static final String CONTROL_DPAD = "dpad";
    public static final String CONTROL_ANALOG = "analog";
    public static final String CONTROL_ACTION_BUTTONS = "action_buttons";
    public static final String CONTROL_L_BUTTON = "l_button";
    public static final String CONTROL_R_BUTTON = "r_button";
    public static final String CONTROL_START = "start";
    public static final String CONTROL_SELECT = "select";
    
    // Setting keys
    private static final String KEY_LAYOUT_PRESET = "layout_preset";
    private static final String KEY_SNAP_TO_GRID = "snap_to_grid";
    
    // Preset values
    public static final String PRESET_DEFAULT = "default";
    public static final String PRESET_COMPACT = "compact";
    public static final String PRESET_WIDE = "wide";
    public static final String PRESET_CUSTOM = "custom";
    
    private SharedPreferences prefs;
    private Context context;
    
    // Default positions (as percentage of screen width/height)
    private static final float[][] DEFAULT_POSITIONS = {
        // {posX%, posY%, scale, opacity, visible}
        {0.05f, 0.35f, 1.0f, 1.0f, 1.0f},  // DPAD
        {0.18f, 0.70f, 1.0f, 1.0f, 1.0f},  // ANALOG
        {0.75f, 0.35f, 1.0f, 1.0f, 1.0f},  // ACTION_BUTTONS
        {0.05f, 0.08f, 1.0f, 1.0f, 1.0f},  // L_BUTTON
        {0.75f, 0.08f, 1.0f, 1.0f, 1.0f},  // R_BUTTON
        {0.60f, 0.85f, 1.0f, 1.0f, 1.0f},  // START
        {0.30f, 0.85f, 1.0f, 1.0f, 1.0f},  // SELECT
    };
    
    // Compact layout positions
    private static final float[][] COMPACT_POSITIONS = {
        {0.02f, 0.40f, 0.8f, 1.0f, 1.0f},  // DPAD
        {0.12f, 0.75f, 0.8f, 1.0f, 1.0f},  // ANALOG
        {0.80f, 0.40f, 0.8f, 1.0f, 1.0f},  // ACTION_BUTTONS
        {0.02f, 0.05f, 0.8f, 1.0f, 1.0f},  // L_BUTTON
        {0.80f, 0.05f, 0.8f, 1.0f, 1.0f},  // R_BUTTON
        {0.65f, 0.90f, 0.8f, 1.0f, 1.0f},  // START
        {0.25f, 0.90f, 0.8f, 1.0f, 1.0f},  // SELECT
    };
    
    // Wide layout positions (for tablets)
    private static final float[][] WIDE_POSITIONS = {
        {0.08f, 0.30f, 1.2f, 1.0f, 1.0f},  // DPAD
        {0.20f, 0.65f, 1.2f, 1.0f, 1.0f},  // ANALOG
        {0.70f, 0.30f, 1.2f, 1.0f, 1.0f},  // ACTION_BUTTONS
        {0.08f, 0.05f, 1.2f, 1.0f, 1.0f},  // L_BUTTON
        {0.70f, 0.05f, 1.2f, 1.0f, 1.0f},  // R_BUTTON
        {0.58f, 0.85f, 1.2f, 1.0f, 1.0f},  // START
        {0.32f, 0.85f, 1.2f, 1.0f, 1.0f},  // SELECT
    };
    
    private static final String[] CONTROL_NAMES = {
        CONTROL_DPAD, CONTROL_ANALOG, CONTROL_ACTION_BUTTONS,
        CONTROL_L_BUTTON, CONTROL_R_BUTTON, CONTROL_START, CONTROL_SELECT
    };
    
    public LayoutSettingsManager(Context context) {
        this.context = context;
        this.prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
    }
    
    // Preset management
    public String getLayoutPreset() {
        return prefs.getString(KEY_LAYOUT_PRESET, PRESET_DEFAULT);
    }
    
    public void setLayoutPreset(String preset) {
        prefs.edit().putString(KEY_LAYOUT_PRESET, preset).apply();
    }
    
    // Snap to grid
    public boolean isSnapToGrid() {
        return prefs.getBoolean(KEY_SNAP_TO_GRID, false);
    }
    
    public void setSnapToGrid(boolean enabled) {
        prefs.edit().putBoolean(KEY_SNAP_TO_GRID, enabled).apply();
    }
    
    // Top bar visibility
    public boolean isTopBarVisible() {
        return prefs.getBoolean("top_bar_visible", true);
    }
    
    public void setTopBarVisible(boolean visible) {
        prefs.edit().putBoolean("top_bar_visible", visible).apply();
    }
    
    // Position getters/setters (as percentage 0.0 - 1.0)
    public float getPositionX(String controlId) {
        int index = getControlIndex(controlId);
        return prefs.getFloat(controlId + "_pos_x", DEFAULT_POSITIONS[index][0]);
    }
    
    public float getPositionY(String controlId) {
        int index = getControlIndex(controlId);
        return prefs.getFloat(controlId + "_pos_y", DEFAULT_POSITIONS[index][1]);
    }
    
    public void setPosition(String controlId, float posX, float posY) {
        prefs.edit()
            .putFloat(controlId + "_pos_x", posX)
            .putFloat(controlId + "_pos_y", posY)
            .apply();
        
        // When custom position is set, switch to custom preset
        if (!getLayoutPreset().equals(PRESET_CUSTOM)) {
            setLayoutPreset(PRESET_CUSTOM);
        }
    }
    
    // Scale getters/setters (0.5 - 2.0)
    public float getScale(String controlId) {
        int index = getControlIndex(controlId);
        return prefs.getFloat(controlId + "_scale", DEFAULT_POSITIONS[index][2]);
    }
    
    public void setScale(String controlId, float scale) {
        // Clamp to valid range
        scale = Math.max(0.5f, Math.min(2.0f, scale));
        prefs.edit().putFloat(controlId + "_scale", scale).apply();
        
        if (!getLayoutPreset().equals(PRESET_CUSTOM)) {
            setLayoutPreset(PRESET_CUSTOM);
        }
    }
    
    // Opacity getters/setters (0.0 - 1.0)
    public float getOpacity(String controlId) {
        int index = getControlIndex(controlId);
        return prefs.getFloat(controlId + "_opacity", DEFAULT_POSITIONS[index][3]);
    }
    
    public void setOpacity(String controlId, float opacity) {
        // Clamp to valid range
        opacity = Math.max(0.0f, Math.min(1.0f, opacity));
        prefs.edit().putFloat(controlId + "_opacity", opacity).apply();
        
        if (!getLayoutPreset().equals(PRESET_CUSTOM)) {
            setLayoutPreset(PRESET_CUSTOM);
        }
    }
    
    // Visibility getters/setters
    public boolean isVisible(String controlId) {
        int index = getControlIndex(controlId);
        return prefs.getBoolean(controlId + "_visible", DEFAULT_POSITIONS[index][4] == 1.0f);
    }
    
    public void setVisible(String controlId, boolean visible) {
        prefs.edit().putBoolean(controlId + "_visible", visible).apply();
        
        if (!getLayoutPreset().equals(PRESET_CUSTOM)) {
            setLayoutPreset(PRESET_CUSTOM);
        }
    }
    
    // Lock position
    public boolean isLocked(String controlId) {
        return prefs.getBoolean(controlId + "_locked", false);
    }
    
    public void setLocked(String controlId, boolean locked) {
        prefs.edit().putBoolean(controlId + "_locked", locked).apply();
    }
    
    // Apply preset
    public void applyPreset(String preset) {
        float[][] positions;
        
        switch (preset) {
            case PRESET_COMPACT:
                positions = COMPACT_POSITIONS;
                break;
            case PRESET_WIDE:
                positions = WIDE_POSITIONS;
                break;
            case PRESET_DEFAULT:
            default:
                positions = DEFAULT_POSITIONS;
                break;
        }
        
        SharedPreferences.Editor editor = prefs.edit();
        
        for (int i = 0; i < CONTROL_NAMES.length; i++) {
            String controlId = CONTROL_NAMES[i];
            editor.putFloat(controlId + "_pos_x", positions[i][0]);
            editor.putFloat(controlId + "_pos_y", positions[i][1]);
            editor.putFloat(controlId + "_scale", positions[i][2]);
            editor.putFloat(controlId + "_opacity", positions[i][3]);
            editor.putBoolean(controlId + "_visible", positions[i][4] == 1.0f);
            editor.putBoolean(controlId + "_locked", false);
        }
        
        editor.putString(KEY_LAYOUT_PRESET, preset);
        editor.apply();
    }
    
    // Reset single control to default
    public void resetControl(String controlId) {
        int index = getControlIndex(controlId);
        
        prefs.edit()
            .putFloat(controlId + "_pos_x", DEFAULT_POSITIONS[index][0])
            .putFloat(controlId + "_pos_y", DEFAULT_POSITIONS[index][1])
            .putFloat(controlId + "_scale", DEFAULT_POSITIONS[index][2])
            .putFloat(controlId + "_opacity", DEFAULT_POSITIONS[index][3])
            .putBoolean(controlId + "_visible", DEFAULT_POSITIONS[index][4] == 1.0f)
            .putBoolean(controlId + "_locked", false)
            .apply();
    }
    
    // Reset all to default
    public void resetAll() {
        applyPreset(PRESET_DEFAULT);
    }
    
    // Helper to get control index
    private int getControlIndex(String controlId) {
        for (int i = 0; i < CONTROL_NAMES.length; i++) {
            if (CONTROL_NAMES[i].equals(controlId)) {
                return i;
            }
        }
        return 0; // Default to first control
    }
    
    // Get all control IDs
    public static String[] getAllControlIds() {
        return CONTROL_NAMES.clone();
    }
    
    // Data class for control settings
    public static class ControlSettings {
        public float posX;
        public float posY;
        public float scale;
        public float opacity;
        public boolean visible;
        public boolean locked;
        
        public ControlSettings(float posX, float posY, float scale, float opacity, boolean visible, boolean locked) {
            this.posX = posX;
            this.posY = posY;
            this.scale = scale;
            this.opacity = opacity;
            this.visible = visible;
            this.locked = locked;
        }
    }
    
    // Get all settings for a control
    public ControlSettings getControlSettings(String controlId) {
        return new ControlSettings(
            getPositionX(controlId),
            getPositionY(controlId),
            getScale(controlId),
            getOpacity(controlId),
            isVisible(controlId),
            isLocked(controlId)
        );
    }
}
