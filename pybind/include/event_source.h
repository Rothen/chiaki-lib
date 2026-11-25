#ifndef CHIAKY_PY_EVENT_SOURCE_H
#define CHIAKY_PY_EVENT_SOURCE_H

#include <functional>
#include <exception>
#include <vector>
#include <algorithm>
#include <string>

#include <chiaki/discovery.h>

#include <pybind11/pybind11.h>
#include <pybind11/functional.h>
#include <pybind11/stl.h>
#include <stdexcept>
#include <iostream>
#include <mutex>

namespace py = pybind11;

template <typename T>
class EventSource
{
public:
    struct Subscription
    {
        std::function<void(const py::object &)> on_next;
        std::function<void(const int32_t, const std::string &)> on_error;
        std::function<void()> on_completed;
        bool active = true;
        EventSource<T> *parent = nullptr;

        void unsubscribe()
        {
            active = false;

            if (parent)
            {
                parent->cleanup_subscribers();
            }
        }
    };

    std::function<void()> on_subscribe;

    EventSource() { }

    EventSource(const EventSource &other)
    {
        subscribers = other.subscribers; // Deep copy subscriber list
    }

    // Copy Assignment Operator
    EventSource &operator=(const EventSource &other)
    {
        if (this == &other)
        {
            return *this;
        }
        std::lock_guard<std::mutex> lock(subscribers_mutex);
        subscribers = other.subscribers;
        return *this;
    }

    ~EventSource()
    {
        // std::cout << "EventSource destroyed at " << this << std::endl;
    }

    void set_on_subscribe(std::function<void()> on_subscribe)
    {
        this->on_subscribe = on_subscribe;
    }

    void next(const T &value) const
    {
        py::gil_scoped_acquire gil;
        py::object arg;
        try
        {
            arg = py::cast(value);
        }
        catch (py::error_already_set &e)
        {
            e.discard_as_unraisable("converting an event for its Python subscribers");
            return;
        }
        call_on_next(arg);
    }

    void next() const
    {
        py::gil_scoped_acquire gil;
        call_on_next(py::none());
    }

    void error(const int code, const std::string &message) const
    {
        py::gil_scoped_acquire gil;
        std::lock_guard<std::mutex> lock(subscribers_mutex);

        for (auto &sub : subscribers)
        {
            if (sub.active && sub.on_error)
            {
                sub.on_error(code, message);
            }
        }
    }

    void completed()
    {
        has_completed = true;
        py::gil_scoped_acquire gil;
        std::lock_guard<std::mutex> lock(subscribers_mutex);
        for (auto &sub : subscribers)
        {
            if (sub.active && sub.on_completed)
            {
                sub.on_completed();
            }
        }
        subscribers.clear();
    }

    Subscription &subscribe(
        std::function<void(const py::object &)> on_next,
        std::function<void(const int32_t, const std::string &)> on_error = py::none(),
        std::function<void()> on_completed = py::none())
    {
        py::gil_scoped_acquire gil;
        if (has_completed)
        {
            throw std::runtime_error("Cannot subscribe to a completed EventSource");
        }
        std::lock_guard<std::mutex> lock(subscribers_mutex);
        subscribers.push_back(Subscription{on_next, on_error, on_completed, true, this});
        if (!has_started)
        {
            has_started = true;
            if (on_subscribe)
            {
                on_subscribe();
            }
        }
        return subscribers.back();
    }

private:
    // Called with the GIL held, usually from one of chiaki's threads. The callbacks are called
    // without holding subscribers_mutex, so that a callback, or a thread it wakes up, can
    // unsubscribe without a deadlock. An exception a callback raises is printed like one in a
    // thread (sys.unraisablehook): if it got back into chiaki's C code, it would end the process.
    void call_on_next(const py::object &arg) const
    {
        std::vector<std::function<void(const py::object &)>> callbacks;
        {
            std::lock_guard<std::mutex> lock(subscribers_mutex);
            for (auto &sub : subscribers)
                if (sub.active && sub.on_next)
                    callbacks.push_back(sub.on_next);
        }
        for (auto &callback : callbacks)
        {
            try
            {
                callback(arg);
            }
            catch (py::error_already_set &e)
            {
                e.discard_as_unraisable("an event subscriber's on_next callback");
            }
        }
    }

    mutable std::mutex subscribers_mutex;
    std::vector<Subscription> subscribers;
    bool has_started = false;
    bool has_completed = false;

    void cleanup_subscribers()
    {
        py::gil_scoped_acquire gil;
        std::lock_guard<std::mutex> lock(subscribers_mutex);
        subscribers.erase(
            std::remove_if(subscribers.begin(), subscribers.end(),
                           [](const Subscription &sub)
                           { return !sub.active; }),
            subscribers.end());
    }
};

#endif // CHIAKY_PY_EVENT_SOURCE_H