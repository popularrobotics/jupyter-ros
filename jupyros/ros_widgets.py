try:
    import rospy
except:
    print("The rospy package is not found in your $PYTHONPATH. Subscribe and publish are not going to work.")
    print("Do you need to activate your ROS environment?")
try:
    from cv_bridge import CvBridge, CvBridgeError
    import cv2
    bridge = CvBridge()
except:
    print("CV Bridge is not installed, please install it to publish Images ")
    print("sudo apt-get install ros-$(rosversion -d)-cv-bridge")
import bqplot as bq
import ipywidgets as widgets
import numpy as np
import threading

def add_widgets(msg_instance, widget_dict, widget_list, prefix=''):
    """
    Adds widgets.
    
    @param msg_type The message type
    @param widget_dict The form list
    @param widget_list The widget list
    
    @return widget_dict and widget_list
    """
    # import only here so non ros env doesn't block installation
    from genpy import Message
    if msg_instance._type.split('/')[-1] == 'Image':
        w = widgets.Text()
        widget_dict['img'] = w
        w_box = widgets.HBox([widgets.Label(value='Image path:'), w])
        widget_list.append(w_box)
        return widget_dict, widget_list

    for idx, slot in enumerate(msg_instance.__slots__):
        attr = getattr(msg_instance, slot)
        s_t = msg_instance._slot_types[idx]
        w = None

        if s_t in ['float32', 'float64']:
            w = widgets.FloatSlider()
        if s_t in ['int8', 'uint8', 'int32', 'uint32', 'int64', 'uint64']:
            w = widgets.IntSlider()
        if s_t in ['string']:
            w = widgets.Text()

        if isinstance(attr, Message):
            widget_list.append(widgets.Label(value=slot))
            widget_dict[slot] = {}
            add_widgets(attr, widget_dict[slot], widget_list, slot)

        if w:
            widget_dict[slot] = w
            w_box = widgets.HBox([widgets.Label(value=slot), w])
            widget_list.append(w_box)
    return widget_dict, widget_list

def widget_dict_to_msg(msg_instance, d):
    for key in d:
        if isinstance(d[key], widgets.Widget):
            if key == 'img':
                img_msg = img_to_msg(d[key].value)
                for slot in img_msg.__slots__:
                    setattr(msg_instance, slot, getattr(img_msg, slot))
                return
            else:
                setattr(msg_instance, key, d[key].value)
        else:
            submsg = getattr(msg_instance, key)
            widget_dict_to_msg(submsg, d[key])

thread_map = {}

def img_to_msg(imgpath):
    img = cv2.imread(imgpath)
    if img is None:
        raise FileNotFoundError('Image File Not Found')
    else:
        imgmsg = bridge.cv2_to_imgmsg(img)
        return imgmsg
    
def publish(topic, msg_type):
    """
    Create a form widget for message type msg_type.
    This function analyzes the fields of msg_type and creates
    an appropriate widget.
    A publisher is automatically created which publishes to the
    topic given as topic parameter. This allows pressing the 
    "Send Message" button to send the message to ROS.
    
    @param msg_type The message type
    @param topic The topic name to publish to
    
    @return jupyter widget for display
    """
    publisher = rospy.Publisher(topic, msg_type, queue_size=10)

    widget_list = []
    widget_dict = {}

    latch_check = widgets.Checkbox(description="Latch Message")
    rate_field = widgets.IntText(description="Rate", value=5)
    stop_btn = widgets.Button(description="Start")

    def latch_value_change(arg):
        publisher.impl.is_latch = arg['new']

    latch_check.observe(latch_value_change, 'value')

    add_widgets(msg_type(), widget_dict, widget_list)
    send_btn = widgets.Button(description="Send Message")
    
    def send_msg(arg):
        msg_to_send = msg_type()
        widget_dict_to_msg(msg_to_send, widget_dict)
        publisher.publish(msg_to_send)

    send_btn.on_click(send_msg)

    thread_map[topic] = False
    def thread_target():
        d = rospy.Duration(1.0 / float(rate_field.value))
        while thread_map[topic]:
            send_msg(None)
            rospy.sleep(d)

    def start_thread(click_args):
        thread_map[topic] = not thread_map[topic]
        if thread_map[topic]:
            local_thread = threading.Thread(target=thread_target)
            local_thread.start()
            stop_btn.description = "Stop"
        else:
            stop_btn.description = "Start"

    stop_btn.on_click(start_thread)


    btm_box = widgets.HBox((send_btn, latch_check, rate_field, stop_btn))
    widget_list.append(btm_box)
    vbox = widgets.VBox(children=widget_list)
    
    return vbox

def live_plot(plot_string, topic_type, history=100, title=None):
    topic = plot_string[:plot_string.find(':') - 1]
    title = title if title else topic
    fields = plot_string.split(':')[1:]
    x_sc = bq.LinearScale()
    y_sc = bq.LinearScale()

    ax_x = bq.Axis(label='X', scale=x_sc, grid_lines='solid')
    ax_y = bq.Axis(label='Y', scale=y_sc, orientation='vertical', grid_lines='solid')

    lines = bq.Lines(x=np.array([]), y=np.array([]), scales={'x': x_sc, 'y': y_sc})
    fig = bq.Figure(axes=[ax_x, ax_y], marks=[lines], labels=fields, display_legend=True, title=title)
    data = []

    def cb(msg, data=data):
        data_el = []
        for f in fields:
            data_el.append(getattr(msg, f))
        data.append(data_el)
        data = data[-history:]
        ndat = np.asarray(data).T
        if lines:
            lines.y = ndat
            lines.x = np.arange(len(data))

    rospy.Subscriber(topic, topic_type, cb)
    return fig

def bag_player():
    import subprocess, yaml, os
    widget_list = []
    bag_player.sp = None
    bgpath_txt = widgets.Text()
    bgpath_txt.description = "Bag file path:"
    play_btn = widgets.Button(description="Play")
    ibox = widgets.Checkbox(description="Immediate")
    lbox = widgets.Checkbox(description="Loop")
    clockbox = widgets.Checkbox(description="Clock")
    hzbox = widgets.Checkbox(description="Hz")
    que_int = widgets.IntText(value=100, description="Queue size")
    factor_int = widgets.IntText(value=1)
    factor_box = widgets.HBox([widgets.Label("Multiply the publish rate by"), factor_int]) 
    def ply_clk(arg):
        if play_btn.description == "Play":
            info_dict = yaml.load(subprocess.Popen(['rosbag', 'info', '--yaml', bgpath_txt.value],
                stdout=subprocess.PIPE).communicate()[0])
            if info_dict is None:
                raise FileNotFoundError("Can't load Bag!")
            else:
                play_btn.description = "Stop"
                bag_player.sp = subprocess.Popen(['rosbag', 'play', bgpath_txt.value], stdin=subprocess.PIPE)
                print("Bag summary:")
                for key, val in info_dict.items():
                    print(key, ":", val)
        else:
            try:
                os.killpg(os.getpgid(bag_player.sp.pid), subprocess.signal.SIGINT)
            except KeyboardInterrupt:
                pass
            play_btn.description = "Play"
    play_btn.on_click(ply_clk)
    options_hbox = widgets.HBox([ibox, lbox, clockbox, hzbox])
    btm_box = widgets.VBox([bgpath_txt, options_hbox, que_int, factor_box, play_btn])
    widget_list.append(btm_box)
    vbox = widgets.VBox(children=widget_list)
    return vbox

