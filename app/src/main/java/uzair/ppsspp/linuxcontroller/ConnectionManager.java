package uzair.ppsspp.linuxcontroller;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONException;
import org.json.JSONObject;

/**
 * Manages connection to the Linux/Windows server and sends commands.
 */
public class ConnectionManager implements TcpClient.TcpListener {
    
    private static final String PREFS_NAME = "psp_controller_prefs";
    private static final String PREF_IP = "server_ip";
    private static final String PREF_PORT = "server_port";
    
    private Context context;
    private TcpClient tcpClient;
    private ConnectionListener listener;
    private SharedPreferences prefs;
    private boolean isConnected = false;
    private long lastPingTime = 0;
    
    public interface ConnectionListener {
        void onConnected();
        void onDisconnected();
        void onConnectionError(String message);
        void onLatencyUpdate(long latencyMs);
        void onLayoutPreview(String controlId, float x, float y, float scale, float opacity, boolean visible);
        void onSetLayout(String layoutJson);
        void onStreamStart(String url, int port, int width, int height);
        void onStreamStop();
        void onStreamError(String message);
    }
    
    public ConnectionManager(Context context) {
        this.context = context;
        this.prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        
        if (context instanceof ConnectionListener) {
            this.listener = (ConnectionListener) context;
        }
    }
    
    public void connect(String ip, int port) {
        // Save for next time
        prefs.edit()
            .putString(PREF_IP, ip)
            .putInt(PREF_PORT, port)
            .apply();
        
        // Disconnect existing connection
        if (tcpClient != null) {
            tcpClient.shutdown();
        }
        
        // Connect
        tcpClient = new TcpClient(this);
        tcpClient.connect(ip, port);
    }
    
    public void disconnect() {
        if (tcpClient != null) {
            tcpClient.shutdown();
            tcpClient = null;
        }
        isConnected = false;
        if (listener != null) {
            listener.onDisconnected();
        }
    }
    
    public String getSavedIp() {
        return prefs.getString(PREF_IP, "");
    }
    
    public int getSavedPort() {
        return prefs.getInt(PREF_PORT, 5555);
    }
    
    public boolean isConnected() {
        return isConnected && tcpClient != null && tcpClient.isConnected();
    }
    
    public void sendButtonPress(String button) {
        sendButton(button, "press");
    }
    
    public void sendButtonRelease(String button) {
        sendButton(button, "release");
    }
    
    private void sendButton(String button, String action) {
        if (!isConnected()) return;
        
        try {
            JSONObject json = new JSONObject();
            json.put("type", "button");
            json.put("button", button);
            json.put("action", action);
            tcpClient.send(json.toString());
        } catch (JSONException e) {
            e.printStackTrace();
        }
    }
    
    public void sendAnalog(float x, float y) {
        if (!isConnected()) return;
        
        try {
            JSONObject json = new JSONObject();
            json.put("type", "analog");
            json.put("x", x);
            json.put("y", y);
            tcpClient.send(json.toString());
        } catch (JSONException e) {
            e.printStackTrace();
        }
    }
    
    public void sendPing() {
        if (!isConnected()) return;
        
        lastPingTime = System.currentTimeMillis();
        try {
            JSONObject json = new JSONObject();
            json.put("type", "ping");
            json.put("timestamp", lastPingTime);
            tcpClient.send(json.toString());
        } catch (JSONException e) {
            e.printStackTrace();
        }
    }
    
    /**
     * Request stream from server with phone's screen dimensions.
     */
    public void requestStream(int width, int height) {
        if (!isConnected()) return;
        
        try {
            JSONObject json = new JSONObject();
            json.put("type", "request_stream");
            json.put("width", width);
            json.put("height", height);
            json.put("fps", 30);
            json.put("quality", 60);
            tcpClient.send(json.toString());
        } catch (JSONException e) {
            e.printStackTrace();
        }
    }
    
    /**
     * Request to stop the stream.
     */
    public void stopStream() {
        if (!isConnected()) return;
        
        try {
            JSONObject json = new JSONObject();
            json.put("type", "stop_stream");
            tcpClient.send(json.toString());
        } catch (JSONException e) {
            e.printStackTrace();
        }
    }
    
    // TcpClient.TcpListener implementation
    
    @Override
    public void onConnected() {
        isConnected = true;
        if (listener != null) {
            listener.onConnected();
        }
        // Send initial ping
        sendPing();
        // Send device info for layout editor
        sendDeviceInfo();
    }
    
    /**
     * Send device info (screen dimensions, density) to server for layout editor.
     */
    public void sendDeviceInfo() {
        if (!isConnected()) return;
        
        try {
            android.util.DisplayMetrics metrics = context.getResources().getDisplayMetrics();
            JSONObject json = new JSONObject();
            json.put("type", "device_info");
            json.put("width", metrics.widthPixels);
            json.put("height", metrics.heightPixels);
            json.put("density", metrics.density);
            tcpClient.send(json.toString());
        } catch (JSONException e) {
            e.printStackTrace();
        }
    }
    
    /**
     * Send current layout (all control positions, scales, opacities) to server.
     * The desktop Layout Editor will use this to initialize with phone's current layout.
     */
    public void sendCurrentLayout(LayoutSettingsManager layoutManager) {
        if (!isConnected()) return;
        
        try {
            JSONObject json = new JSONObject();
            json.put("type", "current_layout");
            
            JSONObject controls = new JSONObject();
            String[] controlIds = LayoutSettingsManager.getAllControlIds();
            
            for (String controlId : controlIds) {
                LayoutSettingsManager.ControlSettings settings = layoutManager.getControlSettings(controlId);
                JSONObject controlJson = new JSONObject();
                controlJson.put("x", settings.posX);
                controlJson.put("y", settings.posY);
                controlJson.put("scale", settings.scale);
                controlJson.put("opacity", settings.opacity);
                controlJson.put("visible", settings.visible);
                controls.put(controlId, controlJson);
            }
            
            json.put("controls", controls);
            tcpClient.send(json.toString());
        } catch (JSONException e) {
            e.printStackTrace();
        }
    }

    
    @Override
    public void onDisconnected() {
        isConnected = false;
        if (listener != null) {
            listener.onDisconnected();
        }
    }
    
    @Override
    public void onError(String message) {
        isConnected = false;
        if (listener != null) {
            listener.onConnectionError(message);
        }
    }
    
    @Override
    public void onMessageReceived(String message) {
        // Handle server responses
        try {
            JSONObject json = new JSONObject(message);
            String type = json.optString("type");
            
            if ("pong".equals(type)) {
                // Calculate latency
                long now = System.currentTimeMillis();
                long latency = now - lastPingTime;
                if (listener != null) {
                    listener.onLatencyUpdate(latency);
                }
            } else if ("layout_preview".equals(type)) {
                // Live preview from desktop editor
                if (listener != null) {
                    String controlId = json.optString("control");
                    float x = (float) json.optDouble("x", -1);
                    float y = (float) json.optDouble("y", -1);
                    float scale = (float) json.optDouble("scale", -1);
                    float opacity = (float) json.optDouble("opacity", -1);
                    boolean visible = json.optBoolean("visible", true);
                    listener.onLayoutPreview(controlId, x, y, scale, opacity, visible);
                }
            } else if ("set_layout".equals(type)) {
                // Save layout from desktop editor
                if (listener != null) {
                    JSONObject layout = json.optJSONObject("layout");
                    if (layout != null) {
                        listener.onSetLayout(layout.toString());
                    }
                }
            } else if ("stream_start".equals(type)) {
                // Stream started - contains URL to connect to
                if (listener != null) {
                    String url = json.optString("url");
                    int port = json.optInt("port", 5556);
                    int width = json.optInt("width", 720);
                    int height = json.optInt("height", 1280);
                    listener.onStreamStart(url, port, width, height);
                }
            } else if ("stream_stop".equals(type)) {
                // Stream stopped
                if (listener != null) {
                    listener.onStreamStop();
                }
            } else if ("stream_error".equals(type)) {
                // Stream error
                if (listener != null) {
                    String errorMsg = json.optString("message", "Stream error");
                    listener.onStreamError(errorMsg);
                }
            }
        } catch (JSONException e) {
            // Ignore parse errors
        }
    }
}
