package uzair.ppsspp.linuxcontroller;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.PrintWriter;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * TCP client for communicating with the Linux server.
 */
public class TcpClient {
    
    private static final int CONNECT_TIMEOUT = 5000;  // 5 seconds
    private static final int READ_TIMEOUT = 3000;      // 3 seconds
    
    private Socket socket;
    private PrintWriter writer;
    private BufferedReader reader;
    private ExecutorService executor;
    private AtomicBoolean connected = new AtomicBoolean(false);
    private TcpListener listener;
    
    public interface TcpListener {
        void onConnected();
        void onDisconnected();
        void onError(String message);
        void onMessageReceived(String message);
    }
    
    public TcpClient(TcpListener listener) {
        this.listener = listener;
        this.executor = Executors.newSingleThreadExecutor();
    }
    
    public void connect(String host, int port) {
        executor.execute(() -> {
            try {
                socket = new Socket();
                socket.connect(new InetSocketAddress(host, port), CONNECT_TIMEOUT);
                socket.setSoTimeout(READ_TIMEOUT);
                socket.setTcpNoDelay(true);  // Disable Nagle's algorithm for lower latency
                
                writer = new PrintWriter(socket.getOutputStream(), true);
                reader = new BufferedReader(new InputStreamReader(socket.getInputStream()));
                
                connected.set(true);
                
                if (listener != null) {
                    listener.onConnected();
                }
                
                // Start reading responses
                startReading();
                
            } catch (IOException e) {
                if (listener != null) {
                    listener.onError("Connection failed: " + e.getMessage());
                }
            }
        });
    }
    
    private void startReading() {
        new Thread(() -> {
            try {
                while (connected.get()) {
                    try {
                        String line = reader.readLine();
                        if (line == null) {
                            // Server closed connection
                            disconnect();
                            break;
                        }
                        if (listener != null) {
                            listener.onMessageReceived(line);
                        }
                    } catch (IOException e) {
                        // Timeout is expected, continue
                        if (!connected.get()) {
                            break;
                        }
                    }
                }
            } catch (Exception e) {
                if (connected.get()) {
                    disconnect();
                }
            }
        }).start();
    }
    
    public void send(String message) {
        if (connected.get() && writer != null) {
            executor.execute(() -> {
                try {
                    writer.println(message);
                    writer.flush();
                } catch (Exception e) {
                    if (listener != null) {
                        listener.onError("Send failed: " + e.getMessage());
                    }
                }
            });
        }
    }
    
    public void disconnect() {
        connected.set(false);
        
        try {
            if (writer != null) {
                writer.close();
                writer = null;
            }
            if (reader != null) {
                reader.close();
                reader = null;
            }
            if (socket != null && !socket.isClosed()) {
                socket.close();
                socket = null;
            }
        } catch (IOException e) {
            // Ignore close errors
        }
        
        if (listener != null) {
            listener.onDisconnected();
        }
    }
    
    public boolean isConnected() {
        return connected.get() && socket != null && socket.isConnected() && !socket.isClosed();
    }
    
    public void shutdown() {
        disconnect();
        executor.shutdown();
    }
}
