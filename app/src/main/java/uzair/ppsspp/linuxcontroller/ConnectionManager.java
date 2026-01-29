package uzair.ppsspp.linuxcontroller;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONException;
import org.json.JSONObject;

/**
 * Manages connection to the Linux server and sends commands.
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
    
    public interface ConnectionListener {
        void onConnected();
        void onDisconnected();
        void onConnectionError(String message);
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
        
        try {
            JSONObject json = new JSONObject();
            json.put("type", "ping");
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
        // Handle server responses if needed
        // Currently just for ack/pong
    }
}
