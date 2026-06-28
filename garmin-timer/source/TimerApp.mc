import Toybox.Application;
import Toybox.Lang;
import Toybox.WatchUi;

class TimerApp extends Application.AppBase {

    function initialize() {
        AppBase.initialize();
    }

    function onStart(state as Dictionary?) as Void {
    }

    function onStop(state as Dictionary?) as Void {
    }

    function getInitialView() as [Views] or [Views, InputDelegates] {
        var view = new TimerView();
        var delegate = new TimerDelegate(view);
        return [view, delegate];
    }
}

function getApp() as TimerApp {
    return Application.getApp() as TimerApp;
}
