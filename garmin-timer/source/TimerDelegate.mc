import Toybox.Lang;
import Toybox.WatchUi;

class TimerDelegate extends WatchUi.BehaviorDelegate {

    private var _view as TimerView;

    function initialize(view as TimerView) {
        BehaviorDelegate.initialize();
        _view = view;
    }

    // Center button or touchscreen tap → start / pause / restart
    function onSelect() as Boolean {
        _view.toggleStartPause();
        return true;
    }

    // Back/lap button → reset to idle with current duration
    function onBack() as Boolean {
        _view.reset();
        return true;
    }

    // Menu button (long-press UP on some devices) → also resets
    function onMenu() as Boolean {
        _view.reset();
        return true;
    }

    // UP button → increase duration by 1 minute (IDLE only)
    function onNextPage() as Boolean {
        _view.adjustDuration(1);
        return true;
    }

    // DOWN button → decrease duration by 1 minute (IDLE only)
    function onPreviousPage() as Boolean {
        _view.adjustDuration(-1);
        return true;
    }
}
