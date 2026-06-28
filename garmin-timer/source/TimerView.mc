import Toybox.Attention;
import Toybox.Graphics;
import Toybox.Lang;
import Toybox.Timer;
import Toybox.WatchUi;

// Timer states
const STATE_IDLE     = 0;
const STATE_RUNNING  = 1;
const STATE_PAUSED   = 2;
const STATE_COMPLETE = 3;

class TimerView extends WatchUi.View {

    private var _durationSecs  as Number;
    private var _remainingSecs as Number;
    private var _state         as Number;
    private var _timer         as Timer.Timer or Null;

    function initialize() {
        View.initialize();
        _durationSecs  = 5 * 60; // default 5 minutes
        _remainingSecs = _durationSecs;
        _state         = STATE_IDLE;
        _timer         = null;
    }

    function onLayout(dc as Dc) as Void {
    }

    function onShow() as Void {
    }

    function onHide() as Void {
        _stopInternalTimer();
    }

    function onUpdate(dc as Dc) as Void {
        var w  = dc.getWidth();
        var h  = dc.getHeight();
        var cx = w / 2;
        var cy = h / 2;

        // Background
        dc.setColor(Graphics.COLOR_BLACK, Graphics.COLOR_BLACK);
        dc.clear();

        // --- Arc ring ---
        var arcRadius = (cx * 0.82).toNumber();
        dc.setPenWidth(10);

        if (_state == STATE_COMPLETE) {
            // Solid green ring when done
            dc.setColor(Graphics.COLOR_GREEN, Graphics.COLOR_TRANSPARENT);
            dc.drawCircle(cx, cy, arcRadius);
        } else if (_state == STATE_RUNNING || _state == STATE_PAUSED) {
            // Dim background ring
            dc.setColor(0x303030, Graphics.COLOR_TRANSPARENT);
            dc.drawCircle(cx, cy, arcRadius);

            // Colored progress arc (sweeps clockwise from the top)
            var progress    = _remainingSecs.toFloat() / _durationSecs.toFloat();
            var sweepAngle  = (progress * 360.0).toNumber();
            var arcColor    = (_state == STATE_PAUSED) ? Graphics.COLOR_YELLOW : 0x0080FF;

            dc.setColor(arcColor, Graphics.COLOR_TRANSPARENT);
            if (sweepAngle > 0) {
                dc.drawArc(cx, cy, arcRadius, Graphics.ARC_CLOCKWISE, 90, 90 - sweepAngle);
            }
        }

        dc.setPenWidth(1);

        // --- Time display ---
        var hours   = _remainingSecs / 3600;
        var minutes = (_remainingSecs % 3600) / 60;
        var seconds = _remainingSecs % 60;

        var timeStr;
        if (hours > 0) {
            timeStr = hours.format("%d") + ":" + minutes.format("%02d") + ":" + seconds.format("%02d");
        } else {
            timeStr = minutes.format("%02d") + ":" + seconds.format("%02d");
        }

        var timeFont   = Graphics.FONT_NUMBER_HOT;
        var fontHeight = dc.getFontHeight(timeFont);

        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
        dc.drawText(cx, cy - fontHeight / 2, timeFont, timeStr, Graphics.TEXT_JUSTIFY_CENTER);

        // --- State label ---
        var stateStr   as String;
        var stateColor as Number;

        if (_state == STATE_IDLE) {
            stateStr   = "READY";
            stateColor = Graphics.COLOR_LT_GRAY;
        } else if (_state == STATE_RUNNING) {
            stateStr   = "RUNNING";
            stateColor = 0x0080FF;
        } else if (_state == STATE_PAUSED) {
            stateStr   = "PAUSED";
            stateColor = Graphics.COLOR_YELLOW;
        } else {
            stateStr   = "DONE!";
            stateColor = Graphics.COLOR_GREEN;
        }

        dc.setColor(stateColor, Graphics.COLOR_TRANSPARENT);
        dc.drawText(cx, cy + fontHeight / 2 + 6, Graphics.FONT_SMALL, stateStr, Graphics.TEXT_JUSTIFY_CENTER);

        // --- Button hint bar at bottom ---
        var hintStr as String;
        if (_state == STATE_IDLE) {
            hintStr = "UP/DN: +/-1min   SEL: Start";
        } else if (_state == STATE_RUNNING) {
            hintStr = "SEL: Pause   BCK: Reset";
        } else if (_state == STATE_PAUSED) {
            hintStr = "SEL: Resume   BCK: Reset";
        } else {
            hintStr = "SEL: Restart   BCK: New";
        }

        dc.setColor(Graphics.COLOR_DK_GRAY, Graphics.COLOR_TRANSPARENT);
        dc.drawText(cx, h - 20, Graphics.FONT_XTINY, hintStr, Graphics.TEXT_JUSTIFY_CENTER);
    }

    // -----------------------------------------------------------------------
    // Public control API (called by TimerDelegate)
    // -----------------------------------------------------------------------

    function toggleStartPause() as Void {
        if (_state == STATE_IDLE || _state == STATE_PAUSED) {
            _state = STATE_RUNNING;
            _startInternalTimer();
        } else if (_state == STATE_RUNNING) {
            _state = STATE_PAUSED;
            _stopInternalTimer();
        } else if (_state == STATE_COMPLETE) {
            // Restart from the same duration
            _remainingSecs = _durationSecs;
            _state = STATE_RUNNING;
            _startInternalTimer();
        }
        WatchUi.requestUpdate();
    }

    function reset() as Void {
        _stopInternalTimer();
        _remainingSecs = _durationSecs;
        _state = STATE_IDLE;
        WatchUi.requestUpdate();
    }

    // Adjust duration by deltaMins minutes (only in IDLE state)
    function adjustDuration(deltaMins as Number) as Void {
        if (_state != STATE_IDLE) {
            return;
        }
        _durationSecs += deltaMins * 60;
        if (_durationSecs < 60) {
            _durationSecs = 60;       // minimum 1 minute
        }
        if (_durationSecs > 36000) {
            _durationSecs = 36000;    // maximum 10 hours
        }
        _remainingSecs = _durationSecs;
        WatchUi.requestUpdate();
    }

    // -----------------------------------------------------------------------
    // Internal timer machinery
    // -----------------------------------------------------------------------

    private function _startInternalTimer() as Void {
        _timer = new Timer.Timer();
        (_timer as Timer.Timer).start(method(:onTick), 1000, true);
    }

    private function _stopInternalTimer() as Void {
        if (_timer != null) {
            (_timer as Timer.Timer).stop();
            _timer = null;
        }
    }

    // Called every second by the internal Timer (must be public for method reference)
    function onTick() as Void {
        if (_remainingSecs > 0) {
            _remainingSecs -= 1;
        }
        if (_remainingSecs == 0) {
            _state = STATE_COMPLETE;
            _stopInternalTimer();
            _alertComplete();
        }
        WatchUi.requestUpdate();
    }

    private function _alertComplete() as Void {
        if (Attention has :vibrate) {
            var pattern = [
                new Attention.VibeProfile(100, 500),
                new Attention.VibeProfile(0,   250),
                new Attention.VibeProfile(100, 500),
                new Attention.VibeProfile(0,   250),
                new Attention.VibeProfile(100, 500)
            ] as Array<Attention.VibeProfile>;
            Attention.vibrate(pattern);
        }
    }
}
